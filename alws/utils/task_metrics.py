"""
Per-task timing for dramatiq actors.

``TaskMetricsMiddleware`` gives every message a ``TaskContext`` held in a
context variable. Low-level hooks add the time they spend to it:

* SQLAlchemy cursor events (``install_db_hooks``) -> ``db`` / ``pulp_db``
* ``PulpClient.request`` -> ``pulp_http`` and ``pulp_semaphore``
* ``PulpClient.wait_for_task`` -> ``pulp_task_wait``

When the message finishes, the middleware publishes the totals per component,
plus ``business`` (wall time minus all of the above), queue wait and total
duration. ``stage()`` / ``observe_stage()`` time named business steps.

The context propagates by itself: dramatiq calls ``before_process_message``
and the actor in the same worker thread, ``run_until_complete`` copies that
thread's context into its task, and ``asyncio.gather`` children copy it
again. All of them hold a reference to the same ``TaskContext``.

Concurrent work (``asyncio.gather`` over Pulp calls) is summed per call, so a
component can exceed the wall time; ``business`` is clamped at zero. Read
components as "time spent waiting on X", not as exact slices of wall time.

This middleware must stay separate from dramatiq's own ``Prometheus``
middleware, which the broker already installs by default: it defines no
``forks`` and only uses ``albs_*`` names, and its samples are served by the
existing exposition server on :9191.

``prometheus_client`` must not be imported at module level here.
``prometheus_client`` picks in-memory or multiprocess storage once, when it is
first imported, and dramatiq only sets ``PROMETHEUS_MULTIPROC_DIR`` in
``after_process_boot``, after ``alws.dramatiq`` and everything it pulls in
have been imported. An early import would leave the whole worker process
in-memory, so neither these metrics nor dramatiq's own ``dramatiq_*`` ones
would reach :9191. ``_metrics()`` therefore imports it and creates the
histograms on first use, which in a worker happens after boot.
"""

import asyncio
import contextlib
import functools
import logging
import re
import threading
import time
import typing
import urllib.parse
from contextvars import ContextVar

import dramatiq
from sqlalchemy import event
from sqlalchemy.engine import Engine, make_url

__all__ = [
    "COMPONENTS",
    "TaskContext",
    "TaskMetricsMiddleware",
    "add_time",
    "current_task",
    "install_db_hooks",
    "observe_pulp_request",
    "observe_stage",
    "pulp_endpoint_label",
    "pulp_polling",
    "stage",
    "timed_stage",
]

# Components that are measured directly; "business" is derived from them.
COMPONENTS = ("db", "pulp_db", "pulp_http", "pulp_semaphore", "pulp_task_wait")
NO_ACTOR = "none"

_logger = logging.getLogger(__name__)

_TASK_BUCKETS = (
    0.5, 1, 2.5, 5, 10, 15, 30, 60, 120, 180, 300, 450, 600, 900, 1800, 3600,
)
_COMPONENT_BUCKETS = (0.01, 0.05, 0.1, 0.25) + _TASK_BUCKETS
_QUERY_COUNT_BUCKETS = (
    0, 1, 5, 10, 25, 50, 100, 250, 500, 1000, 2500, 5000, 10000, 25000,
)
_PULP_REQUEST_BUCKETS = (
    0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10, 30, 60, 120,
)


class _Metrics:
    def __init__(self):
        # Deferred import, see the module docstring.
        from prometheus_client import Histogram

        self.queue_wait = Histogram(
            "albs_task_queue_wait_seconds",
            "Time between enqueueing a dramatiq message and a worker "
            "starting it",
            labelnames=("actor",),
            buckets=_TASK_BUCKETS,
        )
        self.duration = Histogram(
            "albs_task_duration_seconds",
            "Wall time of a dramatiq message, from start to finish",
            labelnames=("actor",),
            buckets=_TASK_BUCKETS,
        )
        self.component = Histogram(
            "albs_task_component_seconds",
            "Time a dramatiq message spent per component (concurrent calls "
            "are summed, so components can exceed wall time)",
            labelnames=("actor", "component"),
            buckets=_COMPONENT_BUCKETS,
        )
        self.db_queries = Histogram(
            "albs_task_db_queries",
            "Number of SQL statements executed by a dramatiq message",
            labelnames=("actor",),
            buckets=_QUERY_COUNT_BUCKETS,
        )
        self.stage = Histogram(
            "albs_task_stage_seconds",
            "Wall time of a named business stage (stages nest; do not sum "
            "them)",
            labelnames=("actor", "stage"),
            buckets=_COMPONENT_BUCKETS,
        )
        self.pulp_request = Histogram(
            "albs_pulp_request_seconds",
            "Pulp HTTP request latency, excluding the wait for the client "
            "semaphore",
            labelnames=("method", "endpoint", "status"),
            buckets=_PULP_REQUEST_BUCKETS,
        )


_metrics_instance: typing.Optional[_Metrics] = None
_metrics_lock = threading.Lock()


def _metrics() -> _Metrics:
    global _metrics_instance
    if _metrics_instance is None:
        with _metrics_lock:
            if _metrics_instance is None:
                _metrics_instance = _Metrics()
    return _metrics_instance


class TaskContext:
    __slots__ = ("actor", "start", "times", "db_queries")

    def __init__(self, actor: str):
        self.actor = actor
        self.start = time.perf_counter()
        self.times = dict.fromkeys(COMPONENTS, 0.0)
        self.db_queries = 0


_task_ctx: ContextVar[typing.Optional[TaskContext]] = ContextVar(
    "albs_task_ctx", default=None
)
# Set while PulpClient.wait_for_task polls, so the polling requests count as
# pulp_task_wait instead of pulp_http/pulp_semaphore.
_pulp_polling: ContextVar[bool] = ContextVar("albs_pulp_polling", default=False)


def current_task() -> typing.Optional[TaskContext]:
    return _task_ctx.get()


def add_time(component: str, seconds: float):
    """Add ``seconds`` to ``component`` of the current task, if there is one."""
    ctx = _task_ctx.get()
    if ctx is not None:
        ctx.times[component] += seconds


def observe_stage(name: str, seconds: float):
    ctx = _task_ctx.get()
    actor = ctx.actor if ctx is not None else NO_ACTOR
    try:
        _metrics().stage.labels(actor, name).observe(seconds)
    except Exception:
        # Called from release/errata code paths: never fail them over metrics.
        _logger.exception("Cannot observe stage %s", name)


@contextlib.contextmanager
def stage(name: str):
    """Time a block as business stage ``name``. ``name`` must be a literal."""
    start = time.perf_counter()
    try:
        yield
    finally:
        observe_stage(name, time.perf_counter() - start)


def timed_stage(name: str):
    """Decorator form of ``stage()`` for sync and async functions."""

    def decorator(func):
        if asyncio.iscoroutinefunction(func):

            @functools.wraps(func)
            async def async_wrapper(*args, **kwargs):
                with stage(name):
                    return await func(*args, **kwargs)

            return async_wrapper

        @functools.wraps(func)
        def sync_wrapper(*args, **kwargs):
            with stage(name):
                return func(*args, **kwargs)

        return sync_wrapper

    return decorator


@contextlib.contextmanager
def pulp_polling():
    """Account everything inside the block as ``pulp_task_wait``."""
    token = _pulp_polling.set(True)
    start = time.perf_counter()
    try:
        yield
    finally:
        _pulp_polling.reset(token)
        add_time("pulp_task_wait", time.perf_counter() - start)


_UUID_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$", re.I
)
_PULP_API_PREFIX = "/pulp/api/v3/"


def pulp_endpoint_label(endpoint: str) -> str:
    """Collapse a Pulp URL or path into a low-cardinality template.

    ``/pulp/api/v3/repositories/rpm/rpm/<uuid>/versions/3/`` becomes
    ``/pulp/api/v3/repositories/rpm/rpm/{id}/versions/{n}/``. Anything that is
    not an API path (served content, repodata) is collapsed entirely.
    """
    path = urllib.parse.urlsplit(endpoint).path
    if not path.startswith("/"):
        path = "/" + path
    if not path.startswith(_PULP_API_PREFIX):
        return "/pulp/content/*" if "/pulp/content/" in path else "other"
    segments = []
    for segment in path.split("/"):
        if _UUID_RE.match(segment):
            segment = "{id}"
        elif segment.isdigit():
            segment = "{n}"
        segments.append(segment)
    return "/".join(segments)


def observe_pulp_request(
    method: str,
    endpoint: str,
    status: str,
    request_seconds: float,
    semaphore_seconds: float,
):
    try:
        _metrics().pulp_request.labels(
            method.upper(), pulp_endpoint_label(endpoint), status
        ).observe(request_seconds)
    except Exception:
        # Called from every Pulp request: never fail it over metrics.
        _logger.exception("Cannot observe Pulp request")
    if _pulp_polling.get():
        return
    add_time("pulp_semaphore", semaphore_seconds)
    add_time("pulp_http", request_seconds)


# --- SQLAlchemy ------------------------------------------------------------

_QUERY_START_KEY = "albs_query_start"
_db_hooks_installed = False
# Engines live for the whole process, so classify each one once.
_engine_components: typing.Dict[str, str] = {}


def _db_target(url) -> tuple:
    url = make_url(url)
    return url.host, url.port, url.database


def _classify_db(url) -> str:
    from alws.config import settings

    target = _db_target(url)
    albs_targets = {
        _db_target(settings.database_url),
        _db_target(settings.sync_database_url),
        _db_target(settings.fastapi_sqla__async__sqlalchemy_url),
    }
    pulp_targets = {
        _db_target(settings.pulp_database_url),
        _db_target(settings.pulp_async_database_url),
    }
    # The ALBS DB wins when both point at the same database (e.g. in tests).
    if target in albs_targets or target not in pulp_targets:
        return "db"
    return "pulp_db"


def _db_component(engine: Engine) -> str:
    key = str(engine.url)
    component = _engine_components.get(key)
    if component is None:
        component = _engine_components[key] = _classify_db(engine.url)
    return component


def _before_cursor_execute(conn, cursor, statement, params, context, many):
    conn.info.setdefault(_QUERY_START_KEY, []).append(time.perf_counter())


def _after_cursor_execute(conn, cursor, statement, params, context, many):
    starts = conn.info.get(_QUERY_START_KEY)
    if not starts:
        return
    elapsed = time.perf_counter() - starts.pop()
    ctx = _task_ctx.get()
    if ctx is None:
        return
    try:
        ctx.times[_db_component(conn.engine)] += elapsed
    except Exception:
        # Runs inside every statement: never fail a query over metrics.
        _logger.exception("Cannot classify database engine")
        ctx.times["db"] += elapsed
    ctx.db_queries += 1


def _handle_error(exception_context):
    conn = exception_context.connection
    if conn is None:
        return
    starts = conn.info.get(_QUERY_START_KEY)
    if starts:
        starts.pop()


def install_db_hooks():
    """Time every SQL statement of every engine, sync and async alike.

    Listening on the ``Engine`` class catches the sync engine that each
    ``AsyncEngine`` wraps, so this works without knowing how fastapi-sqla
    builds its engines. Idempotent.
    """
    global _db_hooks_installed
    if _db_hooks_installed:
        return
    event.listen(Engine, "before_cursor_execute", _before_cursor_execute)
    event.listen(Engine, "after_cursor_execute", _after_cursor_execute)
    event.listen(Engine, "handle_error", _handle_error)
    _db_hooks_installed = True


# --- dramatiq --------------------------------------------------------------


class TaskMetricsMiddleware(dramatiq.Middleware):
    """Publish queue wait, duration and per-component time of each message.

    Never raises: a failure here must not fail or retry the actual task.
    """

    def __init__(self):
        self._local = threading.local()

    def before_process_message(self, broker, message):
        self._local.token = _task_ctx.set(TaskContext(message.actor_name))
        try:
            wait = time.time() - message.message_timestamp / 1000
            _metrics().queue_wait.labels(message.actor_name).observe(
                max(wait, 0.0)
            )
        except Exception:
            _logger.exception("Cannot observe task queue wait")

    def after_process_message(
        self, broker, message, *, result=None, exception=None
    ):
        token = getattr(self._local, "token", None)
        if token is None:
            # Skipped by an earlier middleware before we saw the message.
            return
        self._local.token = None
        try:
            ctx = _task_ctx.get()
            wall = time.perf_counter() - ctx.start
            metrics = _metrics()
            measured = 0.0
            for component, seconds in ctx.times.items():
                measured += seconds
                metrics.component.labels(ctx.actor, component).observe(seconds)
            metrics.component.labels(ctx.actor, "business").observe(
                max(wall - measured, 0.0)
            )
            metrics.duration.labels(ctx.actor).observe(wall)
            metrics.db_queries.labels(ctx.actor).observe(ctx.db_queries)
        except Exception:
            _logger.exception("Cannot publish task metrics")
        finally:
            _task_ctx.reset(token)

    after_skip_message = after_process_message

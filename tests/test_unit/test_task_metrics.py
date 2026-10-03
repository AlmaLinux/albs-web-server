import asyncio
import os
import subprocess
import sys
import time
import uuid

import dramatiq
import pytest
from aiohttp import web
from dramatiq.middleware.prometheus import Prometheus
from prometheus_client import REGISTRY
from sqlalchemy import create_engine, text

from alws.dramatiq import rabbitmq_broker
from alws.utils import task_metrics
from alws.utils.measurements import class_measure_work_time_async
from alws.utils.pulp_client import PulpClient
from alws.utils.task_metrics import (
    COMPONENTS,
    TaskMetricsMiddleware,
    add_time,
    current_task,
    install_db_hooks,
    pulp_endpoint_label,
    stage,
    timed_stage,
)

TASK_UUID = "fd754c2e-3b6c-4d69-9417-6d7f5bdf1e28"


@pytest.fixture(autouse=True)
def disable_pulp_requests():
    # Overrides the global autouse stub: these tests exercise the real
    # PulpClient.request against a local fake Pulp server.
    yield


def sample(name: str, **labels) -> float:
    return REGISTRY.get_sample_value(name, labels) or 0.0


def unique_actor() -> str:
    # The default registry is process-global; a fresh actor label per test
    # keeps assertions independent of what other tests observed.
    return f"test_actor_{uuid.uuid4().hex[:8]}"


def make_message(actor: str, enqueued_seconds_ago: float = 0.0):
    return dramatiq.Message(
        queue_name="test",
        actor_name=actor,
        args=(),
        kwargs={},
        options={},
        message_timestamp=int((time.time() - enqueued_seconds_ago) * 1000),
    )


def run_async(coro):
    # Like the actors: run_until_complete on a loop of our own, leaving the
    # thread's default loop untouched for other tests.
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


def run_task(actor: str, body, enqueued_seconds_ago: float = 0.0):
    """Drive the middleware the way a dramatiq worker thread does."""
    middleware = TaskMetricsMiddleware()
    message = make_message(actor, enqueued_seconds_ago)
    middleware.before_process_message(rabbitmq_broker, message)
    try:
        body()
    finally:
        middleware.after_process_message(rabbitmq_broker, message)


def test_broker_has_single_dramatiq_prometheus_middleware():
    # Registering dramatiq's Prometheus middleware a second time duplicated
    # collectors and fought over :9191 (c35f672); ours must be separate.
    middleware = rabbitmq_broker.middleware
    assert sum(isinstance(m, Prometheus) for m in middleware) == 1
    assert sum(isinstance(m, TaskMetricsMiddleware) for m in middleware) == 1
    task_middleware = next(
        m for m in middleware if isinstance(m, TaskMetricsMiddleware)
    )
    assert not task_middleware.forks


def test_importing_broker_does_not_import_prometheus_client():
    # prometheus_client chooses in-memory vs multiprocess storage on first
    # import, and dramatiq sets PROMETHEUS_MULTIPROC_DIR only after the broker
    # module is imported. Importing it earlier hides every worker metric,
    # dramatiq_* included, from the :9191 exposition server.
    code = (
        "import sys, alws.dramatiq; "
        "sys.exit('prometheus_client' in sys.modules)"
    )
    env = {**os.environ}
    env.pop("PROMETHEUS_MULTIPROC_DIR", None)
    result = subprocess.run(
        [sys.executable, "-c", code], env=env, capture_output=True, text=True
    )
    assert result.returncode == 0, result.stderr or (
        "alws.dramatiq imported prometheus_client at import time"
    )


@pytest.mark.parametrize(
    "endpoint, expected",
    [
        (
            "pulp/api/v3/repositories/rpm/rpm/",
            "/pulp/api/v3/repositories/rpm/rpm/",
        ),
        (
            f"/pulp/api/v3/tasks/{TASK_UUID}/",
            "/pulp/api/v3/tasks/{id}/",
        ),
        (
            f"http://pulp/pulp/api/v3/repositories/rpm/rpm/{TASK_UUID}"
            "/versions/12/?offset=100",
            "/pulp/api/v3/repositories/rpm/rpm/{id}/versions/{n}/",
        ),
        (
            "http://pulp/pulp/content/prod/almalinux-9-baseos/repodata/"
            "repomd.xml",
            "/pulp/content/*",
        ),
        ("http://example.com/whatever", "other"),
    ],
)
def test_pulp_endpoint_label(endpoint, expected):
    assert pulp_endpoint_label(endpoint) == expected


def test_middleware_publishes_components_and_business_time():
    actor = unique_actor()

    async def gathered():
        add_time("pulp_http", 0.5)

    async def main():
        await asyncio.gather(gathered(), gathered())

    def body():
        add_time("db", 1.0)
        # Children of run_until_complete/gather share the same TaskContext.
        run_async(main())
        time.sleep(0.05)

    run_task(actor, body, enqueued_seconds_ago=3)

    assert sample(
        "albs_task_component_seconds_sum", actor=actor, component="db"
    ) == pytest.approx(1.0)
    assert sample(
        "albs_task_component_seconds_sum", actor=actor, component="pulp_http"
    ) == pytest.approx(1.0)
    for component in COMPONENTS + ("business",):
        assert sample(
            "albs_task_component_seconds_count",
            actor=actor,
            component=component,
        ) == 1
    # Measured components (2s) exceed the wall time, so business clamps to 0.
    assert sample(
        "albs_task_component_seconds_sum", actor=actor, component="business"
    ) == 0
    assert sample("albs_task_duration_seconds_count", actor=actor) == 1
    assert sample("albs_task_duration_seconds_sum", actor=actor) >= 0.05
    assert sample(
        "albs_task_queue_wait_seconds_sum", actor=actor
    ) == pytest.approx(3, abs=1)
    assert current_task() is None


def test_middleware_business_time_is_wall_minus_components():
    actor = unique_actor()

    def body():
        time.sleep(0.1)

    run_task(actor, body)

    business = sample(
        "albs_task_component_seconds_sum", actor=actor, component="business"
    )
    wall = sample("albs_task_duration_seconds_sum", actor=actor)
    assert business == pytest.approx(wall)
    assert business >= 0.1


def test_middleware_ignores_message_it_never_started():
    actor = unique_actor()
    # An earlier middleware skipping the message calls after_skip_message
    # without our before_process_message having run.
    TaskMetricsMiddleware().after_skip_message(
        rabbitmq_broker, make_message(actor)
    )
    assert sample("albs_task_duration_seconds_count", actor=actor) == 0


def test_add_time_outside_task_is_noop():
    assert current_task() is None
    add_time("db", 1.0)
    assert current_task() is None


def test_stages_use_task_actor_or_none():
    actor = unique_actor()
    stage_name = f"stage_{uuid.uuid4().hex[:8]}"

    @timed_stage(stage_name)
    async def async_step():
        await asyncio.sleep(0.01)

    def body():
        with stage(stage_name):
            time.sleep(0.01)
        run_async(async_step())

    run_task(actor, body)
    assert sample(
        "albs_task_stage_seconds_count", actor=actor, stage=stage_name
    ) == 2

    with stage(stage_name):
        pass
    assert sample(
        "albs_task_stage_seconds_count", actor="none", stage=stage_name
    ) == 1


def test_metrics_failure_never_breaks_caller(monkeypatch):
    def broken():
        raise OSError("multiprocess dir is gone")

    monkeypatch.setattr(task_metrics, "_metrics", broken)
    with stage("broken_stage"):
        pass
    task_metrics.observe_pulp_request("GET", "pulp/api/v3/tasks/", "200", 1, 0)

    actor = unique_actor()
    contexts = []
    # The middleware swallows it as well, and still tracks the task.
    run_task(actor, lambda: contexts.append(current_task()))
    assert contexts[0] is not None and contexts[0].actor == actor
    assert current_task() is None


def test_db_classification_failure_never_breaks_query(monkeypatch):
    install_db_hooks()
    engine = create_engine("sqlite://")

    def broken(url):
        raise ValueError("bad settings")

    monkeypatch.setattr(task_metrics, "_classify_db", broken)
    monkeypatch.setattr(task_metrics, "_engine_components", {})
    actor = unique_actor()

    def body():
        with engine.connect() as conn:
            assert conn.execute(text("SELECT 1")).scalar() == 1

    run_task(actor, body)
    assert sample("albs_task_db_queries_sum", actor=actor) == 1


def test_db_classification_separates_pulp_db(monkeypatch):
    from alws.config import settings

    monkeypatch.setattr(task_metrics, "_engine_components", {})
    pulp_engine = create_engine(settings.pulp_database_url)
    albs_engine = create_engine(settings.sync_database_url)
    other_engine = create_engine("sqlite://")
    expected_pulp = (
        "db"
        if task_metrics._db_target(settings.pulp_database_url)
        == task_metrics._db_target(settings.sync_database_url)
        else "pulp_db"
    )
    assert task_metrics._db_component(pulp_engine) == expected_pulp
    assert task_metrics._db_component(albs_engine) == "db"
    assert task_metrics._db_component(other_engine) == "db"


def test_class_measure_work_time_async_reports_stage():
    stage_name = f"measured_{uuid.uuid4().hex[:8]}"

    class Planner:
        def __init__(self):
            self.stats = {}

        @class_measure_work_time_async(stage_name)
        async def step(self, value):
            return value * 2

    planner = Planner()
    assert run_async(planner.step(21)) == 42
    assert stage_name in planner.stats
    assert sample(
        "albs_task_stage_seconds_count", actor="none", stage=stage_name
    ) == 1


def test_db_hooks_count_queries_and_time():
    install_db_hooks()
    install_db_hooks()  # idempotent: must not double count
    engine = create_engine("sqlite://")
    actor = unique_actor()
    queries = {}

    def body():
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
            conn.execute(text("SELECT 2"))
        queries["count"] = current_task().db_queries

    run_task(actor, body)

    assert queries["count"] == 2
    assert sample("albs_task_db_queries_sum", actor=actor) == 2
    assert sample(
        "albs_task_component_seconds_sum", actor=actor, component="db"
    ) > 0
    assert sample(
        "albs_task_component_seconds_sum", actor=actor, component="pulp_db"
    ) == 0


def test_db_hooks_recover_from_failed_statement():
    install_db_hooks()
    engine = create_engine("sqlite://")
    actor = unique_actor()

    def body():
        with engine.connect() as conn:
            with pytest.raises(Exception):
                conn.execute(text("SELECT * FROM missing_table"))
            conn.execute(text("SELECT 1"))
            assert not conn.info.get(task_metrics._QUERY_START_KEY)

    run_task(actor, body)
    assert sample("albs_task_db_queries_sum", actor=actor) == 1


async def _start_fake_pulp(handler):
    app = web.Application()
    app.router.add_route("*", "/{tail:.*}", handler)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "127.0.0.1", 0)
    await site.start()
    port = runner.addresses[0][1]
    return runner, f"http://127.0.0.1:{port}/"


def test_pulp_request_is_split_into_http_and_semaphore():
    actor = unique_actor()

    async def handler(request):
        await asyncio.sleep(0.05)
        return web.json_response({"ok": True})

    async def scenario():
        runner, host = await _start_fake_pulp(handler)
        try:
            client = PulpClient(
                host, "admin", "admin", semaphore=asyncio.Semaphore(1)
            )
            # With a semaphore of 1 the second request waits for the first.
            await asyncio.gather(
                client.request("GET", f"pulp/api/v3/tasks/{TASK_UUID}/"),
                client.request("POST", "pulp/api/v3/repositories/rpm/rpm/"),
            )
        finally:
            await runner.cleanup()

    run_task(actor, lambda: run_async(scenario()))

    assert sample(
        "albs_task_component_seconds_sum", actor=actor, component="pulp_http"
    ) >= 0.1
    assert sample(
        "albs_task_component_seconds_sum",
        actor=actor,
        component="pulp_semaphore",
    ) >= 0.04
    assert sample(
        "albs_pulp_request_seconds_count",
        method="GET",
        endpoint="/pulp/api/v3/tasks/{id}/",
        status="200",
    ) >= 1


def test_wait_for_task_counts_as_task_wait_not_http():
    actor = unique_actor()
    polls = {"count": 0}

    async def handler(request):
        polls["count"] += 1
        state = "completed" if polls["count"] >= 3 else "running"
        return web.json_response({"state": state, "pulp_href": request.path})

    async def scenario():
        runner, host = await _start_fake_pulp(handler)
        try:
            client = PulpClient(
                host, "admin", "admin", semaphore=asyncio.Semaphore(5)
            )
            await client.wait_for_task(
                f"pulp/api/v3/tasks/{TASK_UUID}/", sleep_time=0.05
            )
        finally:
            await runner.cleanup()

    run_task(actor, lambda: run_async(scenario()))

    assert polls["count"] == 3
    assert sample(
        "albs_task_component_seconds_sum",
        actor=actor,
        component="pulp_task_wait",
    ) >= 0.1
    assert sample(
        "albs_task_component_seconds_sum", actor=actor, component="pulp_http"
    ) == 0
    assert sample(
        "albs_task_component_seconds_sum",
        actor=actor,
        component="pulp_semaphore",
    ) == 0


def test_pulp_request_error_status_is_labelled():
    async def handler(request):
        return web.json_response({"detail": "nope"}, status=404)

    endpoint = f"pulp/api/v3/content/rpm/packages/{TASK_UUID}/"
    before = sample(
        "albs_pulp_request_seconds_count",
        method="DELETE",
        endpoint="/pulp/api/v3/content/rpm/packages/{id}/",
        status="404",
    )

    async def scenario():
        runner, host = await _start_fake_pulp(handler)
        try:
            client = PulpClient(
                host, "admin", "admin", semaphore=asyncio.Semaphore(5)
            )
            with pytest.raises(Exception):
                await client.request("DELETE", endpoint)
        finally:
            await runner.cleanup()

    run_async(scenario())
    assert sample(
        "albs_pulp_request_seconds_count",
        method="DELETE",
        endpoint="/pulp/api/v3/content/rpm/packages/{id}/",
        status="404",
    ) == before + 1

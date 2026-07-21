"""
Prometheus metrics for albs-web-server.

This module owns the metric definitions, the ASGI app exposed at ``/metrics``,
the HTTP middleware that times every request, and a generic ``track_time``
decorator for instrumenting arbitrary sync/async functions.

Dramatiq workers run in separate processes and are instrumented separately by
the dramatiq worker CLI's built-in Prometheus middleware; they do not go
through this middleware.
"""

import asyncio
import functools
import os
import time

from prometheus_client import (
    CollectorRegistry,
    Counter,
    Histogram,
    make_asgi_app,
    multiprocess,
)
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.routing import Match

__all__ = [
    "PrometheusMiddleware",
    "metrics_app",
    "track_time",
]

_HTTP_BUCKETS = (
    0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10, 30, 60,
)
_FUNC_BUCKETS = (
    0.01, 0.05, 0.1, 0.5, 1, 5, 10, 30, 60, 120, 300, 600,
)

HTTP_REQUEST_DURATION = Histogram(
    "http_request_duration_seconds",
    "HTTP request latency in seconds",
    labelnames=("method", "endpoint", "status"),
    buckets=_HTTP_BUCKETS,
)
HTTP_REQUEST_TOTAL = Counter(
    "http_requests_total",
    "Total HTTP requests",
    labelnames=("method", "endpoint", "status"),
)
FUNCTION_DURATION = Histogram(
    "function_duration_seconds",
    "Runtime of instrumented functions/methods in seconds",
    labelnames=("name",),
    buckets=_FUNC_BUCKETS,
)

# Endpoints we never want to instrument (avoid scrape self-noise).
_EXCLUDED_PATHS = frozenset({"/metrics"})


def metrics_app():
    """Return the ASGI app to mount at ``/metrics``.

    When ``PROMETHEUS_MULTIPROC_DIR`` is set (forked uvicorn workers), expose a
    multiprocess registry that aggregates across worker processes; otherwise
    fall back to the default global registry.
    """
    if os.environ.get("PROMETHEUS_MULTIPROC_DIR"):
        registry = CollectorRegistry()
        multiprocess.MultiProcessCollector(registry)
        return make_asgi_app(registry=registry)
    return make_asgi_app()


def _endpoint_label(request: Request) -> str:
    """Use the matched route template, never the raw path.

    Labelling by raw path turns every path parameter (e.g. each build id) into
    a distinct time series and blows up Prometheus cardinality.

    ``scope["route"]`` is a fast path for frameworks that populate it; plain
    Starlette does not, so we fall back to matching against the app's routes.
    """
    route = request.scope.get("route")
    path = getattr(route, "path", None)
    if path:
        return path
    for candidate in request.app.routes:
        if candidate.matches(request.scope)[0] == Match.FULL:
            return getattr(candidate, "path", None) or "__unmatched__"
    return "__unmatched__"


class PrometheusMiddleware(BaseHTTPMiddleware):
    """Record latency and count for every HTTP request."""

    async def dispatch(self, request: Request, call_next):
        if request.url.path in _EXCLUDED_PATHS:
            return await call_next(request)

        start = time.perf_counter()
        status = 500
        try:
            response = await call_next(request)
            status = response.status_code
            return response
        finally:
            elapsed = time.perf_counter() - start
            labels = (request.method, _endpoint_label(request), str(status))
            HTTP_REQUEST_DURATION.labels(*labels).observe(elapsed)
            HTTP_REQUEST_TOTAL.labels(*labels).inc()


def track_time(name: str):
    """Decorator timing a function into ``function_duration_seconds{name=...}``.

    Works on both sync and async callables, so it can wrap async CRUD helpers
    as well as the sync bodies of dramatiq actors.
    """

    def decorator(func):
        if asyncio.iscoroutinefunction(func):

            @functools.wraps(func)
            async def async_wrapper(*args, **kwargs):
                start = time.perf_counter()
                try:
                    return await func(*args, **kwargs)
                finally:
                    FUNCTION_DURATION.labels(name).observe(
                        time.perf_counter() - start
                    )

            return async_wrapper

        @functools.wraps(func)
        def sync_wrapper(*args, **kwargs):
            start = time.perf_counter()
            try:
                return func(*args, **kwargs)
            finally:
                FUNCTION_DURATION.labels(name).observe(
                    time.perf_counter() - start
                )

        return sync_wrapper

    return decorator

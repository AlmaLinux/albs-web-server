import pytest


@pytest.fixture
def patch_limiter(monkeypatch):
    async def func(*args, **kwargs):
        return

    monkeypatch.setattr("fastapi_limiter.depends.RateLimiter.__call__", func)
    monkeypatch.setattr("alws.utils.limiter.limiter_startup", func)
    monkeypatch.setattr("alws.utils.limiter.limiter_shutdown", func)

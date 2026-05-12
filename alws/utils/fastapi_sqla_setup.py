from fastapi import FastAPI
from fastapi_sqla import setup
from fastapi_sqla.async_sqla import (
    _async_session_factories,
    startup as async_startup,
)
from fastapi_sqla.sqla import _DEFAULT_SESSION_KEY, _session_factories, startup

app = FastAPI()
setup(app)

sync_keys = ['pulp', _DEFAULT_SESSION_KEY]
async_keys = ['async', 'pulp_async']


async def setup_all():
    sync_setup()
    await async_setup()


async def async_setup():
    for key in async_keys:
        existing = _async_session_factories.pop(key, None)
        if existing is not None:
            engine = existing.kw.get('bind')
            if engine is not None:
                await engine.dispose()
        await async_startup(key)


def sync_setup():
    for key in sync_keys:
        existing = _session_factories.pop(key, None)
        if existing is not None:
            engine = existing.kw.get('bind')
            if engine is not None:
                engine.dispose()
        startup(key)

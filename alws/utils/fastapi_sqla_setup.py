from fastapi import FastAPI
from fastapi_sqla import setup
from fastapi_sqla.async_sqla import startup as async_startup
from fastapi_sqla.sqla import _DEFAULT_SESSION_KEY, startup

app = FastAPI()
setup(app)

sync_keys = ['pulp', _DEFAULT_SESSION_KEY]
async_keys = ['async', 'pulp_async']


async def setup_all():
    sync_setup()
    await async_setup()


async def async_setup():
    for key in async_keys:
        await async_startup(key)


def sync_setup():
    for key in sync_keys:
        startup(key)

import asyncio

import importlib
import logging
import threading

from fastapi import FastAPI

from alws import routers
from alws.auth import AuthRoutes
from alws.auth.backend import CookieBackend
from alws.auth.oauth.github import get_github_oauth_client
from alws.auth.schemas import UserRead
from alws.config import settings
from alws.test_scheduler import TestTaskScheduler


logging.basicConfig(level=settings.logging_level)

ROUTERS = [importlib.import_module(f'alws.routers.{module}')
           for module in routers.__all__]
APP_PREFIX = '/api/v1'
AUTH_PREFIX = APP_PREFIX + '/auth'
AUTH_TAG = 'auth'

app = FastAPI(
    prefix=APP_PREFIX
)
scheduler = None
terminate_event = threading.Event()
graceful_terminate_event = threading.Event()


@app.on_event('startup')
async def startup():
    print(settings.database_url)
    global scheduler, terminate_event, graceful_terminate_event
    scheduler = TestTaskScheduler(terminate_event, graceful_terminate_event)
    asyncio.create_task(scheduler.run())


@app.on_event('shutdown')
async def shutdown():
    global terminate_event
    terminate_event.set()


for module in ROUTERS:
    app.include_router(module.router, prefix=APP_PREFIX)
    if getattr(module, 'public_router', None):
        app.include_router(module.public_router, prefix=APP_PREFIX)

github_client = get_github_oauth_client(
    settings.github_client, settings.github_client_secret)

app.include_router(
    AuthRoutes.get_oauth_router(
        github_client,
        CookieBackend,
        settings.jwt_secret,
        associate_by_email=True
    ),
    prefix=AUTH_PREFIX + '/github',
    tags=[AUTH_TAG],
)
app.include_router(
    AuthRoutes.get_oauth_associate_router(
        github_client,
        UserRead,
        settings.jwt_secret,
        requires_verification=False
    ),
    prefix=AUTH_PREFIX + '/associate/github',
    tags=[AUTH_TAG],
)

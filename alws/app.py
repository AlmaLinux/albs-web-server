import asyncio

import importlib
import threading
import uuid

from fastapi import FastAPI
from fastapi_users import FastAPIUsers

from alws.config import settings

import logging
logging.basicConfig(level=settings.logging_level)

from alws import routers
from alws.auth_backend import auth_backend
from alws.config import settings
from alws.models import FastAPIUser
from alws.schemas.user_schema import UserRead, UserCreate, UserUpdate
from alws.test_scheduler import TestTaskScheduler
from alws.users import get_user_manager, SECRET
from alws.utils.github import get_github_oauth_client

fastapi_users = FastAPIUsers[FastAPIUser, uuid.UUID](
    get_user_manager,
    [auth_backend],
)


ROUTERS = [importlib.import_module(f'alws.routers.{module}')
           for module in routers.__all__]
APP_PREFIX = '/api/v1'

app = FastAPI(
    prefix=APP_PREFIX
)
scheduler = None
terminate_event = threading.Event()
graceful_terminate_event = threading.Event()


@app.on_event('startup')
async def startup():
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

app.include_router(
    fastapi_users.get_auth_router(auth_backend),
    prefix=APP_PREFIX + "/auth/jwt",
    tags=["auth"],
)

app.include_router(
    fastapi_users.get_register_router(UserRead, UserCreate),
    prefix=APP_PREFIX + "/auth",
    tags=["auth"],
)

app.include_router(
    fastapi_users.get_verify_router(UserRead),
    prefix=APP_PREFIX + "/auth",
    tags=["auth"],
)

app.include_router(
    fastapi_users.get_reset_password_router(),
    prefix=APP_PREFIX + "/auth",
    tags=["auth"],
)

app.include_router(
    fastapi_users.get_users_router(UserRead, UserUpdate),
    prefix=APP_PREFIX + "/users",
    tags=["users"],
)

app.include_router(
    fastapi_users.get_oauth_router(
        get_github_oauth_client(
            client_id=settings.github_client,
            client_secret=settings.github_client_secret,
        ),
        auth_backend,
        SECRET,
        associate_by_email=True,
    ),
    prefix=APP_PREFIX + "/auth/github",
    tags=["auth"],
)
for route in app.routes:
    print(route.path)

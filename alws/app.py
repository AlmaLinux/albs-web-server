import asyncio

import importlib
import threading

from fastapi import FastAPI

from alws.config import settings

import logging
logging.basicConfig(level=settings.logging_level)

from alws import routers
from alws.test_scheduler import TestTaskScheduler


ROUTERS = [importlib.import_module(f'alws.routers.{module}')
           for module in routers.__all__]
APP_PREFIX = '/api/v1'

app = FastAPI()
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
    if getattr(module, 'copr_router', None):
        app.include_router(module.copr_router)
        continue
    app.include_router(module.router, prefix=APP_PREFIX)
    if getattr(module, 'public_router', None):
        app.include_router(module.public_router, prefix=APP_PREFIX)

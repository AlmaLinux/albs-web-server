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
    for router_type in (
        'router',
        'public_router',
        'copr_router',
    ):
        router = getattr(module, router_type, None)
        if not router:
            continue
        router_params = {'router': router, 'prefix': APP_PREFIX}
        # for correct working COPR features,
        # we don't need prefix for this router
        if router_type == 'copr_router':
            router_params.pop('prefix')
        app.include_router(**router_params)

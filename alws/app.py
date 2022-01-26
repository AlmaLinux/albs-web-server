import importlib
import threading

from fastapi import FastAPI

from alws import routers
from alws.test_scheduler import TestTaskScheduler


ROUTERS = [importlib.import_module(f'alws.routers.{module}')
           for module in routers.__all__]

app = FastAPI(
    prefix='/api/v1/'
)
scheduler = None
terminate_event = threading.Event()
graceful_terminate_event = threading.Event()


@app.on_event('startup')
async def startup():
    global scheduler, terminate_event, graceful_terminate_event
    scheduler = TestTaskScheduler(terminate_event, graceful_terminate_event)
    scheduler.start()


@app.on_event('shutdown')
async def shutdown():
    global terminate_event
    terminate_event.set()


for module in ROUTERS:
    app.include_router(module.router, prefix='/api/v1')

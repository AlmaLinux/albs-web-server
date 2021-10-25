import threading

from fastapi import FastAPI

from alws.routers import (
    builds,
    build_node,
    distro,
    platforms,
    projects,
    releases,
    tests,
    users,
)
from alws.test_scheduler import TestTaskScheduler


app = FastAPI(
    prefix='/api/v1/'
)
scheduler = None
terminate_event = threading.Event()
graceful_terminate_event = threading.Event()


@app.on_event('startup')
async def startup():
    global scheduler, terminate_event, graceful_terminate_event
    # scheduler = TestTaskScheduler(terminate_event, graceful_terminate_event)
    # scheduler.start()


@app.on_event('shutdown')
async def shutdown():
    global terminate_event
    terminate_event.set()


for module in (builds, build_node, distro, platforms, projects, releases,
               tests, users):
    app.include_router(module.router, prefix='/api/v1')

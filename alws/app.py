from fastapi import FastAPI

from alws.routers import builds, platforms, users, build_node, projects


app = FastAPI(
    prefix='/api/v1/'
)


for module in (builds, platforms, users, build_node, projects):
    app.include_router(module.router, prefix='/api/v1')

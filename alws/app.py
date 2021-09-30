from fastapi import FastAPI

from alws.routers import builds, platforms, users, build_node, projects, distro


app = FastAPI(
    prefix='/api/v1/'
)

for module in (builds, platforms, users, build_node, projects, distro):
    app.include_router(module.router, prefix='/api/v1')

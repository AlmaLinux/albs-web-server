import asyncio
from typing import Dict, Any

import dramatiq
from sqlalchemy.future import select

from alws import models
from alws.constants import DRAMATIQ_TASK_TIMEOUT
from alws.crud import build_node as build_node_crud, test
from alws.errors import (
    ArtifactConversionError,
    ModuleUpdateError,
    MultilibProcessingError,
    NoarchProcessingError,
    RepositoryAddError,
    SrpmProvisionError,
)
from alws.build_planner import BuildPlanner
from alws.schemas import build_schema, build_node_schema
from alws.database import SyncSession
from alws.dependencies import get_db
from alws.dramatiq import event_loop


__all__ = ['start_build', 'build_done']


def _sync_fetch_build(db: SyncSession, build_id: int) -> models.Build:
    query = select(models.Build).where(models.Build.id == build_id)
    result = db.execute(query)
    return result.scalars().first()


async def _start_build(build_id: int, build_request: build_schema.BuildCreate):
    with SyncSession() as db:
        with db.begin():
            build = _sync_fetch_build(db, build_id)
            planner = BuildPlanner(
                db,
                build,
                platforms=build_request.platforms,
                is_secure_boot=build_request.is_secure_boot,
                skip_module_checking=build_request.skip_module_checking,
            )
            await planner.load_platforms()
            for task in build_request.tasks:
                await planner.add_task(task)
            for linked_id in build_request.linked_builds:
                linked_build = _sync_fetch_build(db, linked_id)
                if linked_build:
                    await planner.add_linked_builds(linked_build)
            db.flush()
            await planner.init_build_repos()
            db.commit()


async def _build_done(request: build_node_schema.BuildDone):
    async for db in get_db():
        await build_node_crud.build_done(db, request)
        if request.status == 'done':
            await test.create_test_tasks(db, request.task_id)


@dramatiq.actor(
    max_retries=0,
    priority=0
)
def start_build(build_id: int, build_request: Dict[str, Any]):
    parsed_build = build_schema.BuildCreate(**build_request)
    event_loop.run_until_complete(_start_build(build_id, parsed_build))


@dramatiq.actor(
    max_retries=0,
    priority=1,
    time_limit=DRAMATIQ_TASK_TIMEOUT,
    throws=(ArtifactConversionError, ModuleUpdateError,
            MultilibProcessingError, NoarchProcessingError,
            RepositoryAddError, SrpmProvisionError)
)
def build_done(request: Dict[str, Any]):
    parsed_build = build_node_schema.BuildDone(**request)
    event_loop.run_until_complete(_build_done(parsed_build))

import logging
from typing import Dict, Any

import dramatiq
from sqlalchemy.future import select
from sqlalchemy.orm import Session
from sqlalchemy.sql.expression import func

import asyncio
from alws import models
from alws.constants import DRAMATIQ_TASK_TIMEOUT, BuildTaskStatus
from alws.crud import build_node as build_node_crud, platform_flavors, test
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
                platform_flavors=build_request.platform_flavors,
                is_secure_boot=build_request.is_secure_boot,
            )
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
        success = await build_node_crud.safe_build_done(db, request)
        # We don't want to create the test tasks until all build tasks
        # of the same build_id are completed.
        # The last completed task will trigger the creation of the test tasks
        # of the same build.
        all_build_tasks_completed = await _all_build_tasks_completed(db, request.task_id)

        if success and request.status == 'done' and all_build_tasks_completed:
            build_id = await _get_build_id(db, request.task_id)
            await test.create_test_tasks_for_build_id(db, build_id)


async def _create_log_repo(task_id: int):
    async for db in get_db():
        task = await build_node_crud.get_build_task(db, task_id)
        await build_node_crud.create_build_log_repo(db, task)


async def _get_build_id(db: Session, build_task_id: int) -> int:
    async with db.begin():
        build_id = (await db.execute(select(models.BuildTask.build_id).where(
            models.BuildTask.id == build_task_id
        ))).scalars().first()
        return build_id


async def _check_build_and_completed_tasks(
            db: Session,
            build_id: int
        ) -> bool:
    async with db.begin():
        build_tasks = (await db.execute(
            select(func.count()).select_from(models.BuildTask).where(
                models.BuildTask.build_id == build_id
            )
        )).scalar()

        completed_tasks = (await db.execute(
            select(func.count()).select_from(models.BuildTask).where(
                models.BuildTask.build_id == build_id,
                models.BuildTask.status.in_([
                    BuildTaskStatus.COMPLETED,
                    BuildTaskStatus.FAILED,
                    BuildTaskStatus.EXCLUDED,
                ])
            )
        )).scalar()

        return completed_tasks==build_tasks


async def _all_build_tasks_completed(db: Session, build_task_id: int) -> bool:
    build_id = await _get_build_id(db, build_task_id)
    all_completed = await _check_build_and_completed_tasks(db, build_id)
    return all_completed


@dramatiq.actor(
    max_retries=0,
    priority=0,
    time_limit=DRAMATIQ_TASK_TIMEOUT,
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


@dramatiq.actor(
    max_retries=0,
    priority=0,
    time_limit=DRAMATIQ_TASK_TIMEOUT,
)
def create_log_repo(task_id: int):
    event_loop.run_until_complete(_create_log_repo(task_id))

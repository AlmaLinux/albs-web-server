import datetime
import logging
from typing import Dict, Any

import dramatiq

from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.sql.expression import func

from alws import models
from alws.build_planner import BuildPlanner
from alws.constants import DRAMATIQ_TASK_TIMEOUT, BuildTaskStatus
from alws.crud import build_node as build_node_crud
from alws.crud import test
from alws.database import SyncSession
from alws.dependencies import get_db
from alws.dramatiq import event_loop
from alws.errors import (
    ArtifactConversionError,
    ModuleUpdateError,
    MultilibProcessingError,
    NoarchProcessingError,
    RepositoryAddError,
    SrpmProvisionError,
)
from alws.schemas import build_schema, build_node_schema

__all__ = ['start_build', 'build_done']

logger = logging.getLogger(__name__)


def _sync_fetch_build(db: SyncSession, build_id: int) -> models.Build:
    query = select(models.Build).where(models.Build.id == build_id)
    result = db.execute(query)
    return result.scalars().first()


async def _start_build(build_id: int, build_request: build_schema.BuildCreate):
    has_modules = any(
        (
            isinstance(t, build_schema.BuildTaskModuleRef)
            for t in build_request.tasks
        )
    )
    module_build_index = {}

    if has_modules:
        with SyncSession() as db, db.begin():
            platforms = (
                db.execute(
                    select(models.Platform).where(
                        models.Platform.name.in_(
                            [p.name for p in build_request.platforms]
                        )
                    )
                )
                .scalars()
                .all()
            )
            for platform in platforms:
                db.execute(
                    update(models.Platform)
                    .where(models.Platform.id == platform.id)
                    .values(
                        {
                            'module_build_index': models.Platform.module_build_index
                            + 1
                        }
                    )
                )
                db.add(platform)
            db.flush()
            for platform in platforms:
                module_build_index[platform.name] = platform.module_build_index
            db.commit()
            db.close()

    with SyncSession() as db:
        with db.begin():
            build = _sync_fetch_build(db, build_id)
            planner = BuildPlanner(
                db,
                build,
                platforms=build_request.platforms,
                platform_flavors=build_request.platform_flavors,
                is_secure_boot=build_request.is_secure_boot,
                module_build_index=module_build_index,
                logger=logger,
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
        db.close()


async def _build_done(request: build_node_schema.BuildDone):
    async for db in get_db():
        try:
            await build_node_crud.safe_build_done(db, request)
        except Exception as e:
            logger.exception(
                'Unable to complete safe_build_done for build task "%d", '
                'marking it as failed.\nError: %s',
                request.task_id,
                str(e),
            )
            build_task = (
                (
                    await db.execute(
                        select(models.BuildTask).where(
                            models.BuildTask.id == request.task_id
                        )
                    )
                )
                .scalars()
                .first()
            )
            build_task.ts = datetime.datetime.utcnow()
            build_task.error = str(e)
            build_task.status = BuildTaskStatus.FAILED
            await build_node_crud.fast_fail_other_tasks_by_ref(db, build_task)
            await db.commit()

        # We don't want to create the test tasks until all build tasks
        # of the same build_id are completed.
        # The last completed task will trigger the creation of the test tasks
        # of the same build.
        all_build_tasks_completed = await _all_build_tasks_completed(
            db, request.task_id
        )

        if all_build_tasks_completed:
            build_id = await _get_build_id(db, request.task_id)
            try:
                await test.create_test_tasks_for_build_id(db, build_id)
            except Exception as e:
                logger.exception(
                    'Unable to create test tasks for build "%d". Error: %s',
                    build_id,
                    str(e),
                )
            build_id = await _get_build_id(db, request.task_id)
            await db.execute(
                update(models.Build)
                .where(models.Build.id == build_id)
                .values(finished_at=datetime.datetime.utcnow())
            )
            await db.commit()


async def _get_build_id(db: AsyncSession, build_task_id: int) -> int:
    async with db.begin():
        build_id = (
            (
                await db.execute(
                    select(models.BuildTask.build_id).where(
                        models.BuildTask.id == build_task_id
                    )
                )
            )
            .scalars()
            .first()
        )
        return build_id


async def _check_build_and_completed_tasks(
    db: AsyncSession, build_id: int
) -> bool:
    async with db.begin():
        build_tasks = (
            await db.execute(
                select(func.count())
                .select_from(models.BuildTask)
                .where(models.BuildTask.build_id == build_id)
            )
        ).scalar()

        completed_tasks = (
            await db.execute(
                select(func.count())
                .select_from(models.BuildTask)
                .where(
                    models.BuildTask.build_id == build_id,
                    models.BuildTask.status.notin_(
                        [
                            BuildTaskStatus.IDLE,
                            BuildTaskStatus.STARTED,
                        ]
                    ),
                )
            )
        ).scalar()

        return completed_tasks == build_tasks


async def _all_build_tasks_completed(
    db: AsyncSession, build_task_id: int
) -> bool:
    build_id = await _get_build_id(db, build_task_id)
    all_completed = await _check_build_and_completed_tasks(db, build_id)
    return all_completed


@dramatiq.actor(
    max_retries=0,
    priority=0,
    queue_name='builds',
    time_limit=DRAMATIQ_TASK_TIMEOUT,
)
def start_build(build_id: int, build_request: Dict[str, Any]):
    parsed_build = build_schema.BuildCreate(**build_request)
    event_loop.run_until_complete(_start_build(build_id, parsed_build))


@dramatiq.actor(
    max_retries=0,
    priority=1,
    time_limit=DRAMATIQ_TASK_TIMEOUT,
    throws=(
        ArtifactConversionError,
        ModuleUpdateError,
        MultilibProcessingError,
        NoarchProcessingError,
        RepositoryAddError,
        SrpmProvisionError,
    ),
)
def build_done(request: Dict[str, Any]):
    parsed_build = build_node_schema.BuildDone(**request)
    event_loop.run_until_complete(_build_done(parsed_build))

import datetime
import logging
from typing import Any, Dict

import dramatiq
from fastapi_sqla import open_async_session, open_session
from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.orm import Session, joinedload, selectinload
from sqlalchemy.sql.expression import func

from alws import models
from alws.build_planner import BuildPlanner
from alws.config import settings
from alws.constants import (
    DRAMATIQ_TASK_TIMEOUT,
    BuildTaskStatus,
    GitHubIssueStatus,
)
from alws.crud import build_node as build_node_crud
from alws.crud import test
from alws.dependencies import get_async_db_key
from alws.dramatiq import event_loop
from alws.errors import (
    ArtifactConversionError,
    ModuleUpdateError,
    MultilibProcessingError,
    NoarchProcessingError,
    RepositoryAddError,
    SrpmProvisionError,
)
from alws.schemas import build_node_schema, build_schema
from alws.utils.fastapi_sqla_setup import setup_all
from alws.utils.github_integration_helper import (
    find_issues_by_repo_name,
    get_github_client,
    move_issues,
    set_build_id_to_issues,
)

__all__ = ['start_build', 'build_done']

logger = logging.getLogger(__name__)


def _sync_fetch_build(db: Session, build_id: int) -> models.Build:
    query = select(models.Build).where(models.Build.id == build_id)
    result = db.execute(query)
    return result.scalars().first()


async def fetch_build(db: AsyncSession, build_id: int) -> models.Build:
    query = (
        select(models.Build)
        .where(models.Build.id == build_id)
        .options(
            joinedload(models.Build.tasks).selectinload(
                models.BuildTask.rpm_modules
            ),
            joinedload(models.Build.repos),
            joinedload(models.Build.linked_builds),
        )
    )
    result = await db.execute(query)
    return result.scalars().first()


async def _start_build(build_id: int, build_request: build_schema.BuildCreate):
    has_modules = any((
        isinstance(t, build_schema.BuildTaskModuleRef)
        for t in build_request.tasks
    ))
    module_build_index = {}

    if has_modules:
        with open_session() as db:
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
                    .values({
                        'module_build_index': models.Platform.module_build_index
                        + 1
                    })
                )
                db.add(platform)
            db.flush()
            for platform in platforms:
                module_build_index[platform.name] = platform.module_build_index

    async with open_async_session(key=get_async_db_key()) as db:
        build = await fetch_build(db, build_id)
        planner = BuildPlanner(
            db,
            build,
            is_secure_boot=build_request.is_secure_boot,
            module_build_index=module_build_index,
            logger=logger,
        )
        await planner.init(
            platforms=build_request.platforms,
            platform_flavors=build_request.platform_flavors,
        )
        for ref in build_request.tasks:
            await planner.add_git_project(ref)
        for linked_id in build_request.linked_builds:
            linked_build = await fetch_build(db, linked_id)
            if linked_build:
                await planner.add_linked_builds(linked_build)
        await planner.build_dependency_map()
        await db.flush()
        await planner.init_build_repos()

    if settings.github_integration_enabled:
        try:
            github_client = await get_github_client()
            repos = set()
            for task in build_request.tasks:
                if isinstance(task, build_schema.BuildTaskModuleRef):
                    repos.add(f"module {task.module_name}")
                    continue

                repos.add(f"{task.url} {task.git_ref}")
            issues = await find_issues_by_repo_name(
                github_client=github_client,
                repo_names=list(repos),
            )
            if issues:
                await set_build_id_to_issues(
                    github_client=github_client,
                    issues=issues,
                    build_id=build_id,
                )
                await move_issues(
                    github_client=github_client,
                    issues=issues,
                    status=GitHubIssueStatus.BUILDING.value,
                )
        except Exception as err:
            logging.exception(
                "Cannot move issue to the Building section: %s",
                err,
            )


async def _build_done(request: build_node_schema.BuildDone):
    async with open_async_session(key=get_async_db_key()) as db:
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
            await db.flush()

        # We don't want to create the test tasks until all build tasks
        # of the same build_id are completed.
        # The last completed task will trigger the creation of the test tasks
        # of the same build.
        all_build_tasks_completed = await _all_build_tasks_completed(
            db, request.task_id
        )

        if all_build_tasks_completed:
            build_id = await _get_build_id(db, request.task_id)
            cancel_testing = (
                await db.execute(
                    select(models.Build.cancel_testing).where(
                        models.Build.id == build_id
                    )
                )
            ).scalar()
            if not cancel_testing:
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


async def _get_build_id(db: AsyncSession, build_task_id: int) -> int:
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
                models.BuildTask.status.notin_([
                    BuildTaskStatus.IDLE,
                    BuildTaskStatus.STARTED,
                ]),
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
    event_loop.run_until_complete(setup_all())
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
    event_loop.run_until_complete(setup_all())
    event_loop.run_until_complete(_build_done(parsed_build))

"""Restarting the tests of a build, of all packages or only of failed ones.

``build_done`` builds chan for AlmaLinux-8 i686 and x86_64, ``chan_devel``
adds chan-devel to both build tasks, so that each of them tests two packages.
"""

import typing

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from alws import models
from alws.constants import TestTaskStatus as TaskStatus
from alws.crud.test import (
    complete_test_task,
    create_test_tasks_for_build_id,
    restart_build_task_tests,
    restart_build_tests,
)
from alws.schemas import test_schema
from tests.fixtures.tests import install_failed_result, passed_result
from tests.test_utils.pulp_utils import get_artifact_href, get_file_href

pytestmark = pytest.mark.anyio

# Package name and arch of a test task
TaskKey = typing.Tuple[str, str]
LatestTasks = typing.Dict[TaskKey, models.TestTask]

FAILED_TASK = ('chan-devel', 'x86_64')


async def get_latest_test_tasks(
    session: AsyncSession,
    build: models.Build,
) -> LatestTasks:
    """Test tasks of the latest revision of each build task."""
    tasks = (
        (
            await session.execute(
                select(models.TestTask)
                .join(models.BuildTask)
                .where(models.BuildTask.build_id == build.id)
                .options(selectinload(models.TestTask.artifacts))
                .execution_options(populate_existing=True)
            )
        )
        .scalars()
        .all()
    )
    revisions = {}
    for task in tasks:
        revisions[task.build_task_id] = max(
            revisions.get(task.build_task_id, 0),
            task.revision,
        )
    return {
        (task.package_name, task.env_arch): task
        for task in tasks
        if task.revision == revisions[task.build_task_id]
    }


@pytest.fixture
async def chan_devel(
    async_session: AsyncSession,
    regular_build: models.Build,
    build_done,
):
    build_tasks = (
        (
            await async_session.execute(
                select(models.BuildTask).where(
                    models.BuildTask.build_id == regular_build.id,
                    models.BuildTask.arch != 'src',
                )
            )
        )
        .scalars()
        .all()
    )
    for build_task in build_tasks:
        async_session.add(
            models.BuildTaskArtifact(
                build_task_id=build_task.id,
                name=f'chan-devel-0.0.4-3.el8.{build_task.arch}.rpm',
                type='rpm',
                href=get_artifact_href(),
            )
        )
    await async_session.commit()
    await create_test_tasks_for_build_id(async_session, regular_build.id)
    await async_session.commit()


@pytest.fixture
async def tested_build(
    async_session: AsyncSession,
    regular_build: models.Build,
    chan_devel,
) -> LatestTasks:
    """chan-devel has failed on x86_64, everything else has passed."""
    tasks = await get_latest_test_tasks(async_session, regular_build)
    assert sorted(tasks) == [
        ('chan', 'i686'),
        ('chan', 'x86_64'),
        ('chan-devel', 'i686'),
        ('chan-devel', 'x86_64'),
    ]
    for key, task in tasks.items():
        result = passed_result()
        if key == FAILED_TASK:
            result = install_failed_result()
        await complete_test_task(
            async_session,
            task.id,
            test_schema.TestTaskResult(
                api_version='20210512',
                result=result,
                stats={},
            ),
        )
        async_session.add(
            models.TestTaskArtifact(
                name=f'tests_{key[0]}.tap',
                href=get_file_href(),
                test_task_id=task.id,
            )
        )
    await async_session.commit()
    return await get_latest_test_tasks(async_session, regular_build)


async def test_restart_all_tests(
    async_session: AsyncSession,
    regular_build: models.Build,
    tested_build: LatestTasks,
):
    await restart_build_tests(async_session, regular_build.id)
    await async_session.commit()
    tasks = await get_latest_test_tasks(async_session, regular_build)
    for key in (('chan', 'i686'), ('chan-devel', 'i686')):
        assert tasks[key].id == tested_build[key].id
    for key in (('chan', 'x86_64'), FAILED_TASK):
        assert tasks[key].revision == tested_build[key].revision + 1
        assert tasks[key].status == TaskStatus.CREATED


async def test_restart_only_failed_tests(
    async_session: AsyncSession,
    regular_build: models.Build,
    tested_build: LatestTasks,
):
    await restart_build_tests(async_session, regular_build.id, only_failed=True)
    await async_session.commit()
    tasks = await get_latest_test_tasks(async_session, regular_build)
    # The build task without failures isn't restarted at all
    for key in (('chan', 'i686'), ('chan-devel', 'i686')):
        assert tasks[key].id == tested_build[key].id
    failed = tasks[FAILED_TASK]
    assert failed.revision == tested_build[FAILED_TASK].revision + 1
    assert failed.status == TaskStatus.CREATED
    assert failed.alts_response is None
    assert failed.artifacts == []
    # The package that has passed is carried over to the new revision
    passed = tasks[('chan', 'x86_64')]
    old_passed = tested_build[('chan', 'x86_64')]
    assert passed.id != old_passed.id
    assert passed.revision == failed.revision
    assert passed.status == TaskStatus.COMPLETED
    assert passed.alts_response == old_passed.alts_response
    assert passed.finished_at == old_passed.finished_at
    assert [(log.name, log.href) for log in passed.artifacts] == [
        (log.name, log.href) for log in old_passed.artifacts
    ]


async def test_restart_only_failed_build_task_tests(
    async_session: AsyncSession,
    regular_build: models.Build,
    tested_build: LatestTasks,
):
    for key in (('chan', 'i686'), ('chan', 'x86_64')):
        await restart_build_task_tests(
            async_session,
            tested_build[key].build_task_id,
            only_failed=True,
        )
    await async_session.commit()
    tasks = await get_latest_test_tasks(async_session, regular_build)
    # Nothing to restart on i686, all packages have passed there
    for key in (('chan', 'i686'), ('chan-devel', 'i686')):
        assert tasks[key].id == tested_build[key].id
    assert tasks[('chan', 'x86_64')].status == TaskStatus.COMPLETED
    assert tasks[FAILED_TASK].status == TaskStatus.CREATED
    for key in (('chan', 'x86_64'), FAILED_TASK):
        assert tasks[key].revision == tested_build[key].revision + 1

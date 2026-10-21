"""How the package tests config from git affects test tasks.

``build_done`` builds chan from git.almalinux.org/rpms/chan.git for
AlmaLinux-8 i686 and x86_64, so its config is looked up in
git.almalinux.org/tests/chan.
"""

import typing

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from alws import models
from alws.constants import TestTaskStatus as TaskStatus
from alws.crud.test import (
    complete_test_task,
    create_test_tasks_for_build_id,
    get_available_test_tasks,
)
from alws.schemas import test_schema
from tests.fixtures.tests import (
    PackageTestsConfigs,
    install_failed_result,
    passed_result,
)

pytestmark = pytest.mark.anyio

CHAN_CONFIG = """
expected_failures:
  - tests: [install_package]
    packages: [chan]
    platforms: [AlmaLinux-8]
    reason: chan conflicts with a package of the test image
"""
CHAN_CONFIG_URL = (
    'https://git.almalinux.org/tests/chan/src/branch/main/alts.yaml'
)


def alts_result(install_success: bool) -> test_schema.TestTaskResult:
    return test_schema.TestTaskResult(
        api_version='20210512',
        result=passed_result() if install_success else install_failed_result(),
        stats={},
    )


async def get_test_tasks(
    session: AsyncSession,
    build: models.Build,
) -> typing.List[models.TestTask]:
    return (
        (
            await session.execute(
                select(models.TestTask)
                .join(models.BuildTask)
                .where(models.BuildTask.build_id == build.id)
                .order_by(models.TestTask.id)
                .execution_options(populate_existing=True)
            )
        )
        .scalars()
        .all()
    )


async def complete_chan_test_task(
    session: AsyncSession,
    build: models.Build,
    install_success: bool,
) -> models.TestTask:
    task = (await get_test_tasks(session, build))[0]
    await complete_test_task(session, task.id, alts_result(install_success))
    await session.commit()
    return await session.get(
        models.TestTask,
        task.id,
        populate_existing=True,
    )


async def recreate_test_tasks(
    session: AsyncSession,
    build: models.Build,
) -> typing.List[models.TestTask]:
    """Create the next revision of test tasks, as restarting tests does."""
    await create_test_tasks_for_build_id(session, build.id)
    await session.commit()
    tasks = await get_test_tasks(session, build)
    revision = max(task.revision for task in tasks)
    return [task for task in tasks if task.revision == revision]


async def test_failure_without_config(
    async_session: AsyncSession,
    regular_build: models.Build,
    build_done,
):
    task = await complete_chan_test_task(
        async_session,
        regular_build,
        install_success=False,
    )
    assert task.status == TaskStatus.FAILED
    assert 'tests_config' not in task.alts_response


async def test_expected_failure(
    async_session: AsyncSession,
    regular_build: models.Build,
    build_done,
    package_tests_configs: PackageTestsConfigs,
):
    package_tests_configs['chan'] = CHAN_CONFIG
    task = await complete_chan_test_task(
        async_session,
        regular_build,
        install_success=False,
    )
    assert task.status == TaskStatus.COMPLETED
    assert task.alts_response['tests_config'] == {
        'url': CHAN_CONFIG_URL,
        'commit': 'c0ffee',
        'expected_failures': [{
            'test': 'install_package',
            'reason': 'chan conflicts with a package of the test image',
        }],
    }
    # The ALTS response itself stays as it was
    assert task.alts_response['result']['install_package'] == {'success': False}


async def test_failure_on_other_platform(
    async_session: AsyncSession,
    regular_build: models.Build,
    build_done,
    package_tests_configs: PackageTestsConfigs,
):
    package_tests_configs['chan'] = CHAN_CONFIG.replace(
        'AlmaLinux-8',
        'AlmaLinux-9',
    )
    task = await complete_chan_test_task(
        async_session,
        regular_build,
        install_success=False,
    )
    assert task.status == TaskStatus.FAILED
    assert task.alts_response['tests_config'] == {
        'url': CHAN_CONFIG_URL,
        'commit': 'c0ffee',
    }


async def test_unexpected_pass(
    async_session: AsyncSession,
    regular_build: models.Build,
    build_done,
    package_tests_configs: PackageTestsConfigs,
):
    package_tests_configs['chan'] = CHAN_CONFIG
    task = await complete_chan_test_task(
        async_session,
        regular_build,
        install_success=True,
    )
    assert task.status == TaskStatus.COMPLETED
    assert task.alts_response['tests_config']['unexpected_passes'] == [
        'install_package'
    ]


async def test_invalid_config(
    async_session: AsyncSession,
    regular_build: models.Build,
    build_done,
    package_tests_configs: PackageTestsConfigs,
):
    package_tests_configs['chan'] = CHAN_CONFIG.replace('reason', 'reasons')
    task = await complete_chan_test_task(
        async_session,
        regular_build,
        install_success=False,
    )
    assert task.status == TaskStatus.FAILED
    assert task.alts_response['tests_config']['error'].startswith(
        'Invalid config'
    )


async def test_skipped_test_failure(
    async_session: AsyncSession,
    regular_build: models.Build,
    build_done,
    package_tests_configs: PackageTestsConfigs,
):
    package_tests_configs['chan'] = """
skip:
  - tests: install_package
    reason: chan can't be installed in a container
"""
    task = await complete_chan_test_task(
        async_session,
        regular_build,
        install_success=False,
    )
    assert task.status == TaskStatus.COMPLETED
    assert task.alts_response['tests_config'] == {
        'url': CHAN_CONFIG_URL,
        'commit': 'c0ffee',
        'skipped': [{
            'test': 'install_package',
            'reason': "chan can't be installed in a container",
        }],
    }


async def test_skipped_package_result(
    async_session: AsyncSession,
    regular_build: models.Build,
    build_done,
    package_tests_configs: PackageTestsConfigs,
):
    # The config came after the test tasks had been created
    package_tests_configs['chan'] = """
skip:
  - reason: chan isn't tested anymore
"""
    task = await complete_chan_test_task(
        async_session,
        regular_build,
        install_success=False,
    )
    assert task.status == TaskStatus.COMPLETED
    assert task.alts_response['tests_config']['skipped'] == [
        {'test': 'all', 'reason': "chan isn't tested anymore"}
    ]


async def test_skipped_package_is_not_tested(
    async_session: AsyncSession,
    regular_build: models.Build,
    build_done,
    package_tests_configs: PackageTestsConfigs,
):
    package_tests_configs['chan'] = """
skip:
  - packages: chan
    arches: x86_64
    reason: chan can't be tested on x86_64
"""
    tasks = await recreate_test_tasks(async_session, regular_build)
    assert [(task.package_name, task.env_arch) for task in tasks] == [
        ('chan', 'i686')
    ]


async def test_skipped_tests_are_sent_to_alts(
    async_session: AsyncSession,
    regular_build: models.Build,
    build_done,
    package_tests_configs: PackageTestsConfigs,
):
    package_tests_configs['chan'] = """
skip:
  - tests: [uninstall_package, third_party_tests]
    reason: chan can't be removed
  - tests: third_party_tests
    arches: i686
    reason: No third-party tests on i686
"""
    tasks = await recreate_test_tasks(async_session, regular_build)
    assert len(tasks) == 2
    for task in tasks:
        assert task.skipped_tests == ['uninstall_package', 'third_party_tests']
    # Poll like the ALTS scheduler does, the queue may hold other tasks too
    payloads = {}
    while True:
        batch = await get_available_test_tasks(async_session)
        if not batch:
            break
        payloads.update((payload['bs_task_id'], payload) for payload in batch)
    for task in tasks:
        assert payloads[task.id]['skipped_tests'] == [
            'uninstall_package',
            'third_party_tests',
        ]
    # The test tasks that were there before the config skip nothing
    old_tasks = [
        task
        for task in await get_test_tasks(async_session, regular_build)
        if task.revision < tasks[0].revision
    ]
    assert old_tasks
    for task in old_tasks:
        assert 'skipped_tests' not in payloads[task.id]

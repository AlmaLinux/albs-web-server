import asyncio
import datetime
import gzip
import logging
import re
import urllib.parse
from io import BytesIO
from typing import Dict, List, Optional

from sqlalchemy import insert, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.orm import joinedload, selectinload
from sqlalchemy.sql.expression import func

from alws import models
from alws.config import settings
from alws.constants import BuildTaskStatus, TestTaskStatus
from alws.pulp_models import RpmPackage
from alws.schemas import test_schema
from alws.utils.alts_client import AltsClient
from alws.utils.file_utils import download_file
from alws.utils.parsing import parse_tap_output, tap_set_status
from alws.utils.pulp_client import PulpClient
from alws.utils.pulp_utils import (
    get_rpm_packages_by_ids,
    get_uuid_from_pulp_href,
)


def get_repos_for_test_task(task: models.TestTask) -> List[dict]:
    repos = []
    # Build task repos
    build_repositories = [
        {'name': item.name, 'baseurl': item.url}
        for item in task.build_task.build.repos
        if item.type == 'rpm' and item.arch == task.env_arch
    ]

    # Linked build repos
    linked_build_repos = [
        {'name': item.name, 'baseurl': item.url}
        for build in task.build_task.build.linked_builds
        for item in build.repos
        if item.type == 'rpm' and item.arch == task.env_arch
    ]

    # Flavor repos
    platform = task.build_task.platform
    flavor_repos = [
        {
            'name': item.name,
            'baseurl': item.url.replace('$releasever', platform.distr_version),
        }
        for flavor in task.build_task.build.platform_flavors
        for item in flavor.repos
        if item.type == 'rpm' and item.arch == task.env_arch
    ]

    # Repos used in build
    platform_repos = [
        {'name': item.name, 'baseurl': item.url}
        for item in platform.repos
        if item.arch == task.env_arch
    ]

    for repo_arr in (
        build_repositories,
        linked_build_repos,
        flavor_repos,
        platform_repos,
    ):
        repos.extend(repo_arr)

    return repos


async def get_available_test_tasks(session: AsyncSession) -> List[dict]:
    response = []
    updated_tasks = []
    test_tasks = await session.execute(
        select(models.TestTask)
        .where(
            models.TestTask.status == TestTaskStatus.CREATED,
        )
        .with_for_update()
        .options(
            selectinload(models.TestTask.build_task)
            .selectinload(models.BuildTask.build)
            .selectinload(models.Build.repos),
            selectinload(models.TestTask.build_task).selectinload(
                models.BuildTask.ref
            ),
            selectinload(models.TestTask.build_task)
            .selectinload(models.BuildTask.build)
            .selectinload(models.Build.linked_builds)
            .selectinload(models.Build.repos),
            selectinload(models.TestTask.build_task)
            .selectinload(models.BuildTask.build)
            .selectinload(models.Build.platform_flavors)
            .selectinload(models.PlatformFlavour.repos),
            selectinload(models.TestTask.build_task).selectinload(
                models.BuildTask.platform
            ),
            selectinload(models.TestTask.build_task)
            .selectinload(models.BuildTask.platform)
            .selectinload(models.Platform.repos),
            selectinload(models.TestTask.build_task).selectinload(
                models.BuildTask.rpm_modules
            ),
        )
        .order_by(models.TestTask.id.asc())
        .limit(10)
    )
    for task in test_tasks.scalars().all():
        platform = task.build_task.platform
        module_info = next(
            (i for i in task.build_task.rpm_modules if '-devel' not in i.name),
            None,
        )
        module_name = module_info.name if module_info else None
        module_stream = module_info.stream if module_info else None
        module_version = module_info.version if module_info else None
        repositories = get_repos_for_test_task(task)
        task.status = TestTaskStatus.STARTED
        task.scheduled_at = datetime.datetime.utcnow()
        test_configuration = task.build_task.ref.test_configuration
        payload = {
            'bs_task_id': task.id,
            'runner_type': 'docker',
            'dist_name': platform.test_dist_name,
            'dist_version': platform.distr_version,
            'dist_arch': task.env_arch,
            'package_name': task.package_name,
            'package_version': (
                f'{task.package_version}-{task.package_release}'
                if task.package_release
                else task.package_version
            ),
            'callback_href': f'/api/v1/tests/{task.id}/result/',
        }
        if module_name and module_stream and module_version:
            payload.update({
                'module_name': module_name,
                'module_stream': module_stream,
                'module_version': module_version,
            })
        if repositories:
            payload['repositories'] = repositories
        if test_configuration:
            if test_configuration['tests'] is None:
                test_configuration['tests'] = []
            payload['test_configuration'] = test_configuration
        response.append(payload)
        updated_tasks.append(task)
    if updated_tasks:
        session.add_all(updated_tasks)
        await session.flush()
    return response


async def __get_log_repository(
    db: AsyncSession,
    build_id: int,
) -> Optional[models.Repository]:
    build = (
        (
            await db.execute(
                select(models.Build)
                .where(models.Build.id == build_id)
                .options(selectinload(models.Build.repos))
            )
        )
        .scalars()
        .first()
    )
    test_log_repository = next(
        (i for i in build.repos if i.type == 'test_log'),
        None,
    )
    if not test_log_repository:
        raise ValueError(
            'Cannot create test tasks: the log repository is not found'
        )
    return test_log_repository


async def create_test_tasks_for_build_id(db: AsyncSession, build_id: int):
    # We get all build_tasks with the same build_id
    # and whose status is COMPLETED
    build_task_ids = (
        (
            await db.execute(
                select(models.BuildTask.id).where(
                    models.BuildTask.build_id == build_id,
                    models.BuildTask.status == BuildTaskStatus.COMPLETED,
                    models.BuildTask.arch != 'src',
                )
            )
        )
        .scalars()
        .all()
    )

    test_log_repository = await __get_log_repository(db, build_id)

    for build_task_id in build_task_ids:
        await create_test_tasks(db, build_task_id, test_log_repository.id)


def get_pulp_packages(
    artifacts: List[models.BuildTaskArtifact],
) -> Dict[str, RpmPackage]:
    return get_rpm_packages_by_ids(
        [get_uuid_from_pulp_href(artifact.href) for artifact in artifacts],
        [
            RpmPackage.name,
            RpmPackage.version,
            RpmPackage.release,
            RpmPackage.arch,
            RpmPackage.content_ptr_id,
        ],
    )


async def create_test_tasks(
    db: AsyncSession,
    build_task_id: int,
    repository_id: int,
):
    build_task_query = await db.execute(
        select(models.BuildTask)
        .where(
            models.BuildTask.id == build_task_id,
        )
        .options(selectinload(models.BuildTask.artifacts)),
    )
    build_task = build_task_query.scalars().first()

    latest_revision_query = select(
        func.max(models.TestTask.revision),
    ).filter(
        models.TestTask.build_task_id == build_task_id,
    )
    result = await db.execute(latest_revision_query)
    latest_revision = result.scalars().first()
    new_revision = 1
    if latest_revision:
        new_revision = latest_revision + 1

    test_tasks = []
    pulp_packages = get_pulp_packages(build_task.artifacts)
    for artifact in build_task.artifacts:
        if artifact.type != 'rpm':
            continue
        artifact_info = pulp_packages.get(artifact.href)
        if not artifact_info:
            logging.error(
                'Cannot get information about artifact %s with href %s',
                artifact.name,
                artifact.href,
            )
            continue
        if artifact_info.arch == 'src':
            continue
        task = models.TestTask(
            build_task_id=build_task_id,
            package_name=artifact_info.name,
            package_version=artifact_info.version,
            env_arch=build_task.arch,
            status=TestTaskStatus.CREATED,
            revision=new_revision,
            repository_id=repository_id,
        )
        if artifact_info.release:
            task.package_release = artifact_info.release
        test_tasks.append(task)
    if test_tasks:
        db.add_all(test_tasks)
        await db.flush()


async def restart_build_tests(db: AsyncSession, build_id: int):
    # Note that this functionality is triggered by frontend,
    # which only restarts tests for those builds that already
    # had passed the tests
    # Set cancel_testing to False just in case
    await db.execute(
        update(models.Build)
        .where(models.Build.id == build_id)
        .values(cancel_testing=False)
    )
    query = (
        select(models.BuildTask)
        .options(joinedload(models.BuildTask.test_tasks))
        .where(models.BuildTask.build_id == build_id)
    )

    build_tasks = await db.execute(query)
    build_tasks = build_tasks.scalars().unique().all()
    test_log_repository = await __get_log_repository(db, build_id)
    await db.flush()
    for build_task in build_tasks:
        if not build_task.test_tasks:
            continue

        last_revision = build_task.test_tasks[-1].revision
        failed = False
        for test_task in build_task.test_tasks:
            if test_task.revision != last_revision:
                continue

            if test_task.status == TestTaskStatus.FAILED:
                failed = True
                break

        if failed:
            await create_test_tasks(
                db,
                build_task.id,
                test_log_repository.id,
            )


async def restart_build_task_tests(db: AsyncSession, build_task_id: int):
    build_task = (
        (
            await db.execute(
                select(models.BuildTask)
                .where(models.BuildTask.id == build_task_id)
                .options(
                    selectinload(models.BuildTask.build).selectinload(
                        models.Build.repos
                    )
                )
            )
        )
        .scalars()
        .first()
    )
    test_log_repository = next(
        (i for i in build_task.build.repos if i.type == 'test_log'),
        None,
    )
    if not test_log_repository:
        raise ValueError(
            'Cannot create test tasks: the log repository is not found'
        )
    await create_test_tasks(db, build_task_id, test_log_repository.id)


async def cancel_build_tests(db: AsyncSession, build_id: int):
    # Set cancel_testing to True in db
    await db.execute(
        update(models.Build)
        .where(models.Build.id == build_id)
        .values(cancel_testing=True)
    )

    build_task_ids = (
        (
            await db.execute(
                select(models.BuildTask.id).where(
                    models.BuildTask.build_id == build_id
                )
            )
        )
        .scalars()
        .all()
    )

    # Set TestTaskStatus.CANCELLED for those that are still
    # with status TestTaskStatus.CREATED
    await db.execute(
        update(models.TestTask)
        .where(
            models.TestTask.status == TestTaskStatus.CREATED,
            models.TestTask.build_task_id.in_(build_task_ids),
        )
        .values(status=TestTaskStatus.CANCELLED)
    )

    started_test_tasks_ids = (
        (
            await db.execute(
                select(models.TestTask.id).where(
                    models.TestTask.status == TestTaskStatus.STARTED,
                    models.TestTask.build_task_id.in_(build_task_ids),
                )
            )
        )
        .scalars()
        .all()
    )

    await db.flush()
    # Tell ALTS to cancel those with TestTaskStatus.STARTED. ALTS
    # will notify statuses back when its done cancelling tests
    if started_test_tasks_ids:
        logging.info(f'{started_test_tasks_ids=}')
        alts_client = AltsClient(settings.alts_host, settings.alts_token)
        response = await alts_client.cancel_tasks(started_test_tasks_ids)
        logging.info(f'## Cancel ALTS tasks {response=}')


async def __convert_to_file(pulp_client: PulpClient, artifact: dict):
    href = await pulp_client.create_file(artifact['name'], artifact['href'])
    return artifact['name'], href


async def update_test_task(
    db: AsyncSession,
    task_id: int,
    test_result: test_schema.TestTaskResult,
    status: TestTaskStatus = TestTaskStatus.COMPLETED,
):
    started_at = test_result.stats.get('started_at', None)
    if started_at:
        started_at = datetime.datetime.fromisoformat(started_at)
    await db.execute(
        update(models.TestTask)
        .where(models.TestTask.id == task_id)
        .values(
            status=status,
            started_at=started_at,
            finished_at=datetime.datetime.utcnow(),
            alts_response=test_result.model_dump(),
        )
    )
    await db.execute(
        insert(models.PerformanceStats).values(
            test_task_id=task_id,
            statistics=test_result.stats,
        )
    )


async def complete_test_task(
    db: AsyncSession,
    task_id: int,
    test_result: test_schema.TestTaskResult,
):
    pulp_client = PulpClient(
        settings.pulp_host,
        settings.pulp_user,
        settings.pulp_password,
    )
    task = (
        (
            await db.execute(
                select(models.TestTask)
                .where(
                    models.TestTask.id == task_id,
                )
                .options(
                    selectinload(models.TestTask.repository),
                    selectinload(models.TestTask.performance_stats),
                )
            )
        )
        .scalars()
        .first()
    )

    # Logs processing
    logs = []
    new_hrefs = []
    conv_tasks = []
    status = TestTaskStatus.COMPLETED
    for log in test_result.result.get('logs', []):
        if log.get('href'):
            conv_tasks.append(__convert_to_file(pulp_client, log))
        else:
            logging.error('Log file %s is missing href', str(log))
            continue
    try:
        results = await asyncio.gather(*conv_tasks)
        for name, href in results:
            new_hrefs.append(href)
            log_record = models.TestTaskArtifact(
                name=name,
                href=href,
                test_task_id=task_id,
            )
            logs.append(log_record)

        if task.repository:
            await pulp_client.modify_repository(
                task.repository.pulp_href,
                add=new_hrefs,
            )
    except Exception:
        logging.exception('Cannot convert test logs to proper files')
        status = TestTaskStatus.FAILED
    else:
        if test_result.result.get('revoked'):
            status = TestTaskStatus.CANCELLED
        else:
            for key, item in test_result.result.items():
                if key == 'tests':
                    for test_item in item.values():
                        if not test_item.get('success', False):
                            status = TestTaskStatus.FAILED
                            break
                # Skip logs from processing
                elif key == 'logs':
                    continue
                elif not item.get('success', False):
                    status = TestTaskStatus.FAILED
                    break
    finally:
        await update_test_task(db, task_id, test_result, status=status)
        if logs:
            db.add_all(logs)


async def get_test_tasks_by_build_task(
    db: AsyncSession,
    build_task_id: int,
    latest: bool = True,
    revision: Optional[int] = None,
):
    query = (
        select(models.TestTask)
        .where(models.TestTask.build_task_id == build_task_id)
        .options(selectinload(models.TestTask.performance_stats))
    )
    # If latest=False, but revision is not set, should return
    # latest results anyway
    if (not latest and not revision) or latest:
        subquery = (
            select(func.max(models.TestTask.revision))
            .filter(models.TestTask.build_task_id == build_task_id)
            .scalar_subquery()
        )
        query = query.filter(models.TestTask.revision == subquery)
    elif revision:
        query = query.filter(models.TestTask.revision == revision)
    result = await db.execute(query)
    return result.scalars().all()


def get_logs_format(logs: bytes) -> str:
    logs_format = 'text'
    if re.search(
        rb'^Exit code: \d\nStdout:\n\n1\.\.\d',
        logs,
        flags=re.IGNORECASE,
    ):
        logs_format = 'tap'
    return logs_format


async def get_test_logs(build_task_id: int, db: AsyncSession) -> list:
    """
    Parses test logs and determine test format.
    Returns dict of lists for each build's test with detailed status report.

    Parameters
    ----------
    build_task_id : int
        Id of the build, which tests info is interested
    db: Session
        db connection

    Returns
    -------
    list

    """
    test_tasks = (
        select(models.TestTask)
        .where(
            models.TestTask.build_task_id == build_task_id,
            models.TestTask.revision
            == select(func.max(models.TestTask.revision))
            .filter(models.TestTask.build_task_id == build_task_id)
            .scalar_subquery(),
        )
        .options(
            selectinload(models.TestTask.artifacts),
            selectinload(models.TestTask.repository),
        )
    )
    test_tasks = await db.execute(test_tasks)
    test_tasks = test_tasks.scalars().all()

    test_results = []
    for test_task in test_tasks:
        for artifact in test_task.artifacts:
            if not artifact.name.startswith('tests_'):
                continue
            log = BytesIO()
            log_href = urllib.parse.urljoin(
                test_task.repository.url,
                artifact.name,
            )
            await download_file(log_href, log)
            log_content = log.getvalue()
            # on local machines and our stagings
            # we will download logs from pulp directly
            if isinstance(log_content, bytes) and log_content.startswith(
                b'\x1f\x8b'
            ):
                log_content = gzip.decompress(log_content)
            tap_results = parse_tap_output(log_content)
            tap_status = tap_set_status(tap_results)
            logs_format = get_logs_format(log_content)
            test_tap = {
                'id': test_task.id,
                'log': log_content,
                'log_name': artifact.name,
                'success': tap_status,
                'logs_format': logs_format,
                'tap_results': tap_results,
            }
            test_results.append(test_tap)
    return test_results

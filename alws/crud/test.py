import asyncio
import datetime
import gzip
import logging
import re
import typing
import urllib.parse
from io import BytesIO

from sqlalchemy import insert, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.orm import selectinload
from sqlalchemy.sql.expression import func

from alws import models
from alws.config import settings
from alws.constants import BuildTaskStatus, TestTaskStatus
from alws.schemas import test_schema
from alws.utils.pulp_client import PulpClient
from alws.utils.file_utils import download_file
from alws.utils.parsing import parse_tap_output, tap_set_status


async def __get_log_repository(
        db: AsyncSession, build_id: int) -> typing.Optional[models.Repository]:
    build = (await db.execute(select(models.Build).where(
        models.Build.id == build_id).options(
        selectinload(models.Build.repos)
    ))).scalars().first()
    test_log_repository = next(
        (i for i in build.repos if i.type == 'test_log'), None)
    if not test_log_repository:
        raise ValueError('Cannot create test tasks: '
                         'the log repository is not found')
    return test_log_repository


async def create_test_tasks_for_build_id(db: AsyncSession, build_id: int):
    async with db.begin():
        # We get all build_tasks with the same build_id
        # and whose status is COMPLETED
        build_task_ids = (await db.execute(
            select(models.BuildTask.id).where(
                models.BuildTask.build_id == build_id,
                models.BuildTask.status == BuildTaskStatus.COMPLETED
            )
        )).scalars().all()

        test_log_repository = await __get_log_repository(db, build_id)

    for build_task_id in build_task_ids:
        await create_test_tasks(
            db, build_task_id, test_log_repository.id)


async def create_test_tasks(db: AsyncSession, build_task_id: int,
                            repository_id: int):
    pulp_client = PulpClient(
        settings.pulp_host,
        settings.pulp_user,
        settings.pulp_password
    )
    async with db.begin():
        build_task_query = await db.execute(
            select(models.BuildTask).where(
                models.BuildTask.id == build_task_id,
            ).options(selectinload(models.BuildTask.artifacts)),
        )
        build_task = build_task_query.scalars().first()

        latest_revision_query = select(
            func.max(models.TestTask.revision),
        ).filter(
            models.TestTask.build_task_id == build_task_id,
        )
        result = await db.execute(latest_revision_query)
        latest_revision = result.scalars().first()
        if latest_revision:
            new_revision = latest_revision + 1
        else:
            new_revision = 1

        test_tasks = []
        for artifact in build_task.artifacts:
            if artifact.type != 'rpm':
                continue
            artifact_info = None
            try:
                artifact_info = await pulp_client.get_rpm_package(
                    artifact.href,
                    include_fields=['name', 'version', 'release', 'arch']
                )
                if artifact_info['arch'] == 'src':
                    continue
            except Exception:
                logging.exception(
                    'Cannot get information about artifact %s with href %s',
                    artifact.name, artifact.href
                )
            if artifact_info:
                task = models.TestTask(
                    build_task_id=build_task_id,
                    package_name=artifact_info['name'],
                    package_version=artifact_info['version'],
                    env_arch=build_task.arch,
                    status=TestTaskStatus.CREATED,
                    revision=new_revision,
                    repository_id=repository_id,
                )
                if artifact_info.get('release'):
                    task.package_release = artifact_info['release']
                test_tasks.append(task)
        if test_tasks:
            db.add_all(test_tasks)
            await db.commit()


async def restart_build_tests(db: AsyncSession, build_id: int):
    # Note that this functionality is triggered by frontend,
    # which only restarts tests for those builds that already
    # had passed the tests
    build_task_ids = await db.execute(
        select(models.BuildTask.id).where(
            models.BuildTask.build_id == build_id))
    build_task_ids = build_task_ids.scalars().all()
    test_log_repository = await __get_log_repository(db, build_id)
    for build_task_id in build_task_ids:
        await create_test_tasks(db, build_task_id, test_log_repository.id)


async def restart_build_task_tests(db: AsyncSession, build_task_id: int):
    async with db.begin():
        build_task = (await db.execute(select(models.BuildTask).where(
            models.BuildTask.id == build_task_id).options(
            selectinload(models.BuildTask.build).selectinload(
                models.Build.repos)
        ))).scalars().first()
        test_log_repository = next(
            (i for i in build_task.build.repos if i.type == 'test_log'), None)
        if not test_log_repository:
            raise ValueError('Cannot create test tasks: '
                             'the log repository is not found')
        await create_test_tasks(db, build_task_id, test_log_repository.id)


async def __convert_to_file(pulp_client: PulpClient, artifact: dict):
    href = await pulp_client.create_file(artifact['name'], artifact['href'])
    return artifact['name'], href


async def update_test_task(db: AsyncSession, task_id: int,
                           test_result: test_schema.TestTaskResult,
                           status: TestTaskStatus = TestTaskStatus.COMPLETED):
    started_at = test_result.stats.get('started_at', None)
    if started_at:
        started_at = datetime.datetime.fromisoformat(started_at)
    await db.execute(update(models.TestTask).where(
        models.TestTask.id == task_id).values(
        status=status,
        started_at=started_at,
        finished_at=datetime.datetime.utcnow(),
        alts_response=test_result.dict()
    ))
    await db.execute(insert(models.PerformanceStats).values(
        test_task_id=task_id, statistics=test_result.stats))


async def complete_test_task(db: AsyncSession, task_id: int,
                             test_result: test_schema.TestTaskResult):
    pulp_client = PulpClient(
        settings.pulp_host,
        settings.pulp_user,
        settings.pulp_password
    )
    task = (await db.execute(select(models.TestTask).where(
        models.TestTask.id == task_id,
    ).options(
        selectinload(models.TestTask.repository),
        selectinload(models.TestTask.performance_stats)
    ))).scalars().first()

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
                name=name, href=href, test_task_id=task_id)
            logs.append(log_record)

        if task.repository:
            await pulp_client.modify_repository(
                task.repository.pulp_href, add=new_hrefs)
    except Exception:
        logging.exception('Cannot convert test logs to proper files')
        status = TestTaskStatus.FAILED
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
        db: AsyncSession, build_task_id: int, latest: bool = True,
        revision: int = None):
    query = select(models.TestTask).where(
        models.TestTask.build_task_id == build_task_id).options(
        selectinload(models.TestTask.performance_stats)
    )
    # If latest=False, but revision is not set, should return
    # latest results anyway
    if (not latest and not revision) or latest:
        subquery = select(func.max(models.TestTask.revision)).filter(
            models.TestTask.build_task_id == build_task_id).scalar_subquery()
        query = query.filter(models.TestTask.revision == subquery)
    elif revision:
        query = query.filter(models.TestTask.revision == revision)
    result = await db.execute(query)
    return result.scalars().all()


def get_logs_format(logs: bytes) -> str:
    logs_format = 'text'
    if re.search(rb'^Exit code: \d\nStdout:\n\n1\.\.\d',
                 logs, flags=re.IGNORECASE):
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
    test_tasks = select(models.TestTask).where(
        models.TestTask.build_task_id == build_task_id,
    ).options(
        selectinload(models.TestTask.artifacts),
        selectinload(models.TestTask.repository),
    )
    test_tasks = await db.execute(test_tasks)
    test_tasks = test_tasks.scalars().all()

    test_results = []
    for test_task in test_tasks:
        for artifact in test_task.artifacts:
            if not artifact.name.startswith('tests_'):
                continue
            log = BytesIO()
            log_href = urllib.parse.urljoin(test_task.repository.url,
                                            artifact.name)
            await download_file(log_href, log)
            log_content = log.getvalue()
            # on local machines and our stagings
            # we will download logs from pulp directly
            if (
                isinstance(log_content, bytes)
                and log_content.startswith(b'\x1f\x8b')
            ):
                log_content = gzip.decompress(log_content)
            tap_results = parse_tap_output(log_content)
            tap_status = tap_set_status(tap_results)
            logs_format = get_logs_format(log_content)
            test_tap = {
                'id': test_task.id,
                'log': log_content,
                'success': tap_status,
                'logs_format': logs_format,
                'tap_results': tap_results
            }
            test_results.append(test_tap)
    return test_results

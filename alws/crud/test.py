from sqlalchemy.future import select
from sqlalchemy.orm import Session, selectinload
from sqlalchemy.sql.expression import func

from alws import models
from alws.config import settings
from alws.constants import TestTaskStatus
from alws.schemas import test_schema
from alws.utils.pulp_client import PulpClient


async def create_test_tasks(db: Session, build_task_id: int):
    pulp_client = PulpClient(
        settings.pulp_host,
        settings.pulp_user,
        settings.pulp_password
    )
    build_task_query = await db.execute(
        select(models.BuildTask).where(
            models.BuildTask.id == build_task_id)
        .options(selectinload(models.BuildTask.artifacts))
    )
    build_task = build_task_query.scalars().first()

    latest_revision_query = select(
        func.max(models.TestTask.revision)).filter(
        models.TestTask.build_task_id == build_task_id)
    result = await db.execute(latest_revision_query)
    latest_revision = result.scalars().first()
    if latest_revision:
        new_revision = latest_revision + 1
    else:
        new_revision = 1

    # Create logs repository
    repo_name = f'test_logs-btid-{build_task.id}-tr-{new_revision}'
    repo_url, repo_href = await pulp_client.create_log_repo(
        repo_name, distro_path_start='test_logs')

    repository = models.Repository(
        name=repo_name, url=repo_url, arch=build_task.arch,
        pulp_href=repo_href, type='test_log', debug=False
    )
    db.add(repository)
    await db.commit()

    r_query = select(models.Repository).where(
        models.Repository.name == repo_name)
    results = await db.execute(r_query)
    repository = results.scalars().first()

    test_tasks = []
    for artifact in build_task.artifacts:
        if artifact.type != 'rpm':
            continue
        artifact_info = await pulp_client.get_rpm_package(
            artifact.href,
            include_fields=['name', 'version', 'release', 'arch']
        )
        task = models.TestTask(build_task_id=build_task_id,
                               package_name=artifact_info['name'],
                               package_version=artifact_info['version'],
                               env_arch=build_task.arch,
                               status=TestTaskStatus.CREATED,
                               revision=new_revision,
                               repository_id=repository.id)
        if artifact_info.get('release'):
            task.package_release = artifact_info['release']
        test_tasks.append(task)
    db.add_all(test_tasks)
    await db.commit()


async def restart_build_tests(db: Session, build_id: int):
    async with db.begin():
        build_task_ids = await db.execute(
            select(models.BuildTask.id).where(
                models.BuildTask.build_id == build_id))
    for build_task_id in build_task_ids:
        await create_test_tasks(db, build_task_id[0])


async def complete_test_task(db: Session, task_id: int,
                             test_result: test_schema.TestTaskResult):
    pulp_client = PulpClient(
        settings.pulp_host,
        settings.pulp_user,
        settings.pulp_password
    )
    async with db.begin():
        tasks = await db.execute(select(models.TestTask).where(
            models.TestTask.id == task_id).options(
            selectinload(models.TestTask.repository)).with_for_update())
        task = tasks.scalars().first()
        status = TestTaskStatus.COMPLETED
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
        task.status = status
        task.alts_response = test_result.dict()
        logs = []
        for log in test_result.result.get('logs', []):
            if task.repository:
                href = await pulp_client.create_file(
                    log['name'], log['href'], task.repository.pulp_href)
            else:
                href = log['href']
            if not href:
                continue
            log_record = models.TestTaskArtifact(
                name=log['name'], href=href, test_task_id=task.id)
            logs.append(log_record)

        db.add(task)
        db.add_all(logs)
        await db.commit()


async def get_test_tasks_by_build_task(
        db: Session, build_task_id: int, latest: bool = True,
        revision: int = None):
    async with db.begin():
        query = select(models.TestTask).where(
            models.TestTask.build_task_id == build_task_id)
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

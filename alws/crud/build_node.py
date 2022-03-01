import datetime
import logging
import typing

import sqlalchemy
from sqlalchemy import delete, insert, update
from sqlalchemy.future import select
from sqlalchemy.orm import Session, selectinload

from alws import models
from alws.config import settings
from alws.constants import BuildTaskStatus
from alws.schemas import build_node_schema
from alws.utils.modularity import IndexWrapper
from alws.utils.multilib import add_multilib_packages, get_multilib_packages
from alws.utils.noarch import save_noarch_packages
from alws.utils.pulp_client import PulpClient


async def get_available_build_task(
            db: Session,
            request: build_node_schema.RequestTask
        ) -> typing.Optional[models.BuildTask]:
    # TODO: here should be config value
    ts_expired = datetime.datetime.now() - datetime.timedelta(minutes=20)
    query = ~models.BuildTask.dependencies.any()
    db_task = db.execute(
        select(models.BuildTask).where(query).with_for_update().filter(
                sqlalchemy.and_(
                    models.BuildTask.status < BuildTaskStatus.COMPLETED,
                    models.BuildTask.arch.in_(request.supported_arches),
                    sqlalchemy.or_(
                        models.BuildTask.ts < ts_expired,
                        models.BuildTask.ts.__eq__(None)
                    )
                )
            ).options(
            selectinload(models.BuildTask.ref),
            selectinload(models.BuildTask.build).selectinload(
                models.Build.repos),
            selectinload(models.BuildTask.platform).selectinload(
                models.Platform.repos),
            selectinload(models.BuildTask.build).selectinload(
                models.Build.user),
            selectinload(models.BuildTask.build).selectinload(
                models.Build.linked_builds).selectinload(
                models.Build.repos)
        ).order_by(models.BuildTask.id)
    )
    db_task = db_task.scalars().first()
    if not db_task:
        return
    db_task.ts = datetime.datetime.now()
    db_task.status = BuildTaskStatus.STARTED
    return db_task


def add_build_task_dependencies(db: Session, task: models.BuildTask,
                                last_task: models.BuildTask):
    task.dependencies.append(last_task)


async def update_failed_build_items(db: Session, build_id: int):
    query = select(models.BuildTask).where(
        sqlalchemy.and_(
            models.BuildTask.build_id == build_id,
            models.BuildTask.status == BuildTaskStatus.FAILED)
    ).order_by(models.BuildTask.index, models.BuildTask.id)
    last_task = None
    failed_tasks = db.execute(query)
    for task in failed_tasks.scalars():
        task.status = BuildTaskStatus.IDLE
        if last_task is not None:
            db.run_sync(add_build_task_dependencies, task, last_task)
        last_task = task
    db.flush()


async def ping_tasks(
            db: Session,
            task_list: typing.List[int]
        ):
    query = models.BuildTask.id.in_(task_list)
    now = datetime.datetime.now()
    db.execute(update(models.BuildTask).where(query).values(ts=now))
    db.flush()


async def check_build_task_is_finished(db: Session, task_id: int) -> bool:
    build_tasks = db.execute(select(models.BuildTask).where(
        models.BuildTask.id == task_id))
    build_task = build_tasks.scalars().first()
    return BuildTaskStatus.is_finished(build_task.status)


async def __process_rpms(pulp_client: PulpClient, task_id: int, task_arch: str,
                         task_artifacts: list, repositories: list,
                         built_srpm_url: str = None, module_index=None):
    rpms = []
    for artifact in task_artifacts:
        arch = task_arch
        if artifact.arch == 'src':
            arch = artifact.arch
        if arch == 'src' and built_srpm_url is not None:
            continue
        repo = next(
            build_repo for build_repo in repositories
            if build_repo.arch == arch
            and build_repo.type == artifact.type
            and build_repo.debug == artifact.is_debuginfo
        )
        try:
            href = await pulp_client.create_rpm_package(
                artifact.name, artifact.href, repo.pulp_href)
            if module_index:
                for module in module_index.iter_modules():
                    rpm_package = await pulp_client.get_rpm_package(href)
                    module.add_rpm_artifact(rpm_package)
        except Exception as e:
            logging.error('Cannot create RPM package for %s, error: %s',
                          str(artifact), str(e))
            continue
        else:
            rpms.append(
                models.BuildTaskArtifact(
                    build_task_id=task_id,
                    name=artifact.name,
                    type=artifact.type,
                    href=href
                )
            )
    return rpms


async def __process_logs(pulp_client: PulpClient, task_id: int,
                         task_artifacts: list, repositories: list):
    logs = []
    str_task_id = str(task_id)
    for artifact in task_artifacts:
        repo = next(
            repo for repo in repositories
            if repo.name.endswith(str_task_id)
        )
        try:
            href = await pulp_client.create_file(
                artifact.name, artifact.href, repo.pulp_href)
        except Exception as e:
            logging.error('Cannot create log file for %s, error: %s',
                          str(artifact), str(e))
            continue
        else:
            logs.append(
                models.BuildTaskArtifact(
                    build_task_id=task_id,
                    name=artifact.name,
                    type=artifact.type,
                    href=href
                )
            )
    return logs


async def __process_build_task_artifacts(
        db: Session, task_id: int, task_artifacts: list):
    pulp_client = PulpClient(
        settings.pulp_host,
        settings.pulp_user,
        settings.pulp_password
    )
    build_tasks = db.execute(
        select(models.BuildTask).where(
            models.BuildTask.id == task_id).options(
            selectinload(models.BuildTask.platform).selectinload(
                models.Platform.reference_platforms),
            selectinload(models.BuildTask.build).selectinload(
                models.Build.repos
            ),
            selectinload(models.BuildTask.rpm_module)
        ).with_for_update()
    )
    build_task = build_tasks.scalars().first()
    module_index = None
    module_repo = None
    if build_task.rpm_module:
        module_repo = next(
            build_repo for build_repo in build_task.build.repos
            if build_repo.arch == build_task.arch
            and not build_repo.debug
            and build_repo.type == 'rpm'
        )
        try:
            repo_modules_yaml = await pulp_client.get_repo_modules_yaml(
                module_repo.url)
            module_index = IndexWrapper.from_template(repo_modules_yaml)
        except Exception as e:
            logging.error('Cannot parse modules index: %s', str(e))
    rpm_artifacts = [item for item in task_artifacts if item.type == 'rpm']
    log_artifacts = [item for item in task_artifacts
                     if item.type == 'build_log']
    rpm_repositories = [repo for repo in build_task.build.repos
                        if repo.type == 'rpm']
    log_repositories = [repo for repo in build_task.build.repos
                        if repo.type == 'build_log']
    db_entities = []
    db_entities.extend(
        await __process_rpms(
            pulp_client, build_task.id, build_task.arch,
            rpm_artifacts, rpm_repositories,
            built_srpm_url=build_task.built_srpm_url,
            module_index=module_index
        )
    )
    db_entities.extend(
        await __process_logs(pulp_client, build_task.id, log_artifacts,
                             log_repositories)
    )
    if build_task.rpm_module and module_index:
        module_pulp_href, sha256 = await pulp_client.create_module(
            module_index.render(),
            build_task.rpm_module.name,
            build_task.rpm_module.stream,
            build_task.rpm_module.context,
            build_task.rpm_module.arch
        )
        await pulp_client.modify_repository(
            module_repo.pulp_href,
            add=[module_pulp_href],
            remove=[build_task.rpm_module.pulp_href]
        )
        build_task.rpm_module.sha256 = sha256
        build_task.rpm_module.pulp_href = module_pulp_href

    db.add_all(db_entities)
    db.add(build_task)
    db.flush()
    db.refresh(build_task)
    return build_task


async def __update_built_srpm_url(db: Session, build_task: models.BuildTask):
    uncompleted_tasks_ids = []
    if build_task.status in (BuildTaskStatus.COMPLETED,
                             BuildTaskStatus.FAILED):
        uncompleted_tasks_ids = db.execute(
            select(models.BuildTask.id).where(
                models.BuildTask.id != build_task.id,
                models.BuildTask.ref_id == build_task.ref_id,
                models.BuildTask.status < BuildTaskStatus.COMPLETED,
            ),
        )
        uncompleted_tasks_ids = list(uncompleted_tasks_ids.scalars().all())

    # if SRPM doesn't builted in first arch of project,
    # we need to stop building project
    if build_task.status == BuildTaskStatus.FAILED and uncompleted_tasks_ids:
        update_query = update(models.BuildTask).where(
            models.BuildTask.id.in_(uncompleted_tasks_ids),
        ).values(status=BuildTaskStatus.FAILED)
        db.execute(update_query)

        remove_query = delete(models.BuildTaskDependency).where(
            models.BuildTaskDependency.c.build_task_dependency.in_(
                uncompleted_tasks_ids),
        )
        db.execute(remove_query)

    # if SRPM builted we need to download them
    # from pulp repos in next tasks
    if all((build_task.status == BuildTaskStatus.COMPLETED,
            uncompleted_tasks_ids,
            build_task.built_srpm_url is None)):
        srpm_artifact = db.execute(
            select(models.BuildTaskArtifact).where(
                models.BuildTaskArtifact.build_task_id == build_task.id,
                models.BuildTaskArtifact.name.like("%.src.rpm"),
                models.BuildTaskArtifact.type == 'rpm',
            ),
        )
        srpm_artifact = srpm_artifact.scalars().first()

        srpm_url = "{}-src-{}-br/Packages/{}/{}".format(
            build_task.platform.name,
            build_task.build_id,
            srpm_artifact.name[0].lower(),
            srpm_artifact.name,
        )
        insert_values = [
            {'build_task_id': task_id, 'name': srpm_artifact.name,
                'type': 'rpm', 'href': srpm_artifact.href}
            for task_id in uncompleted_tasks_ids
        ]

        update_query = update(models.BuildTask).where(
            models.BuildTask.ref_id == build_task.ref_id,
        ).values(built_srpm_url=srpm_url)
        db.execute(update_query)
        db.execute(insert(models.BuildTaskArtifact), insert_values)

    db.flush()


async def build_done(
            db: Session,
            request: build_node_schema.BuildDone
        ):
    build_task = await __process_build_task_artifacts(
        db, request.task_id, request.artifacts)
    status = BuildTaskStatus.COMPLETED
    if request.status == 'failed':
        status = BuildTaskStatus.FAILED
    elif request.status == 'excluded':
        status = BuildTaskStatus.EXCLUDED
    src_rpm = next((
        artifact.name for artifact in request.artifacts
        if artifact.arch == 'src' and artifact.type == 'rpm'
    ), None)
    multilib_conditions = (
        src_rpm is not None,
        build_task.arch in ('x86_64', 'i686'),
        status == BuildTaskStatus.COMPLETED,
        bool(settings.beholder_host),
        # TODO: Beholder doesn't have authorization right now
        # bool(settings.beholder_token),
    )
    if all(multilib_conditions):
        try:
            multilib_pkgs = await get_multilib_packages(
                db, build_task, src_rpm)
            if multilib_pkgs:
                await add_multilib_packages(db, build_task, multilib_pkgs)
        except Exception as e:
            logging.error('Cannot process multilib packages: %s', str(e))

    db.execute(
        update(models.BuildTask).where(
            models.BuildTask.id == request.task_id).values(status=status)
    )

    try:
        await save_noarch_packages(db, build_task)
    except Exception as e:
        logging.error('Cannot process noarch packages: %s', str(e))

    db.execute(
        delete(models.BuildTaskDependency).where(
            models.BuildTaskDependency.c.build_task_dependency == request.task_id
        )
    )

    rpms_result = db.execute(select(models.BuildTaskArtifact).where(
        models.BuildTaskArtifact.build_task_id == build_task.id,
        models.BuildTaskArtifact.type == 'rpm'))
    srpm = None
    binary_rpms = []
    for rpm in rpms_result.scalars().all():
        if rpm.name.endswith('.src.rpm') and (
                build_task.built_srpm_url is not None):
            continue
        if rpm.name.endswith('.src.rpm'):
            srpm = models.SourceRpm()
            srpm.artifact = rpm
            srpm.build = build_task.build
        else:
            binary_rpm = models.BinaryRpm()
            binary_rpm.artifact = rpm
            binary_rpm.build = build_task.build
            binary_rpms.append(binary_rpm)

    # retrieve already created instance of model SourceRpm
    if not srpm:
        srpms = db.execute(select(models.SourceRpm).where(
            models.SourceRpm.build_id == build_task.build_id))
        srpm = srpms.scalars().first()
    if build_task.built_srpm_url is None:
        db.add(srpm)
        db.flush()
        db.refresh(srpm)
    for binary_rpm in binary_rpms:
        binary_rpm.source_rpm = srpm

    db.add_all(binary_rpms)
    db.flush()

    await __update_built_srpm_url(db, build_task)

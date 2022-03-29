import asyncio
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
from alws.errors import (
    ArtifactConversionError,
    ModuleUpdateError,
    MultilibProcessingError,
    NoarchProcessingError,
    RepositoryAddError,
    SrpmProvisionError,
)
from alws.schemas import build_node_schema
from alws.utils.modularity import IndexWrapper
from alws.utils.multilib import add_multilib_packages, get_multilib_packages
from alws.utils.noarch import save_noarch_packages
from alws.utils.pulp_client import PulpClient


async def get_available_build_task(
            db: Session,
            request: build_node_schema.RequestTask
        ) -> models.BuildTask:
    async with db.begin():
        # TODO: here should be config value
        ts_expired = datetime.datetime.now() - datetime.timedelta(minutes=20)
        query = ~models.BuildTask.dependencies.any()
        db_task = await db.execute(
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
        await db.commit()
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
    async with db.begin():
        last_task = None
        failed_tasks = await db.execute(query)
        for task in failed_tasks.scalars():
            task.status = BuildTaskStatus.IDLE
            if last_task is not None:
                await db.run_sync(add_build_task_dependencies, task, last_task)
            last_task = task
        await db.commit()


async def ping_tasks(
            db: Session,
            task_list: typing.List[int]
        ):
    query = models.BuildTask.id.in_(task_list)
    now = datetime.datetime.now()
    async with db.begin():
        await db.execute(update(models.BuildTask).where(query).values(ts=now))
        await db.commit()


async def check_build_task_is_finished(db: Session, task_id: int) -> bool:
    async with db.begin():
        build_tasks = await db.execute(select(models.BuildTask).where(
            models.BuildTask.id == task_id))
        build_task = build_tasks.scalars().first()
    return BuildTaskStatus.is_finished(build_task.status)


async def __get_rpm_package_info(pulp_client: PulpClient, rpm_href: str) \
        -> (str, dict):
    info = await pulp_client.get_rpm_package(rpm_href)
    return rpm_href, info


async def __process_rpms(pulp_client: PulpClient, task_id: int, task_arch: str,
                         task_artifacts: list, repositories: list,
                         built_srpm_url: str = None, module_index=None):

    def get_repo(repo_arch, is_debug):
        return next(
            build_repo for build_repo in repositories
            if build_repo.arch == repo_arch
            and build_repo.type == 'rpm'
            and build_repo.debug == is_debug
        )

    rpms = []
    arch_repo = get_repo(task_arch, False)
    debug_repo = get_repo(task_arch, True)
    src_repo = get_repo('src', False)
    arch_packages_tasks = []
    src_packages_tasks = []
    debug_packages_tasks = []
    for artifact in task_artifacts:
        if artifact.arch == 'src' and built_srpm_url is None:
            src_packages_tasks.append(pulp_client.create_entity(artifact))
        elif artifact.is_debuginfo:
            debug_packages_tasks.append(pulp_client.create_entity(artifact))
        else:
            arch_packages_tasks.append(pulp_client.create_entity(artifact))

    processed_packages = []
    for tasks, repo in (
            (src_packages_tasks, src_repo), (arch_packages_tasks, arch_repo),
            (debug_packages_tasks, debug_repo)):
        if tasks:
            try:
                results = await asyncio.gather(*tasks)
            except Exception as e:
                logging.exception('Cannot create RPM packages for repo %s',
                                  str(repo))
                raise ArtifactConversionError(
                    'Cannot put RPM packages into Pulp storage: %s', str(e))
            else:
                processed_packages.extend(results)
                hrefs = [item[0] for item in results]
                try:
                    await pulp_client.modify_repository(
                        repo.pulp_href, add=hrefs)
                except Exception as e:
                    logging.exception('Cannot add RPM packages '
                                      'to the repository: %s', e)
                    raise RepositoryAddError(
                        f'Cannot add RPM packages to the repository {str(repo)}')

    for href, artifact in processed_packages:
        rpms.append(
            models.BuildTaskArtifact(
                build_task_id=task_id,
                name=artifact.name,
                type=artifact.type,
                href=href
            )
        )

    if module_index:
        results = await asyncio.gather((__get_rpm_package_info(
            pulp_client, rpm.href) for rpm in rpms))
        packages_info = dict(results)
        try:
            for module in module_index.iter_modules():
                for rpm in rpms:
                    rpm_package = packages_info[rpm.href]
                    module.add_rpm_artifact(rpm_package)
        except Exception as e:
            raise ModuleUpdateError('Cannot update module: %s', str(e)) from e

    return rpms


async def __process_logs(pulp_client: PulpClient, task_id: int,
                         task_artifacts: list, repositories: list):
    logs = []
    str_task_id = str(task_id)
    repo = next(
        repo for repo in repositories
        if repo.name.endswith(str_task_id)
    )
    files = [pulp_client.create_entity(artifact)
             for artifact in task_artifacts]
    try:
        results = await asyncio.gather(*files)
    except Exception as e:
        logging.exception('Cannot create log files for %s', str(repo))
        raise ArtifactConversionError(
            f'Cannot create log files for {str(repo)}, error: {str(e)}')

    hrefs = []
    for href, artifact in results:
        logs.append(
            models.BuildTaskArtifact(
                build_task_id=task_id,
                name=artifact.name,
                type=artifact.type,
                href=href
            )
        )
        hrefs.append(href)
    try:
        await pulp_client.modify_repository(repo.pulp_href, add=hrefs)
    except Exception as e:
        logging.exception('Cannot add log files to the repository: %s',
                          str(e))
        raise RepositoryAddError(
            'Cannot save build log into Pulp repository: %s', str(e))
    return logs


async def __process_build_task_artifacts(
        db: Session, task_id: int, task_artifacts: list):
    pulp_client = PulpClient(
        settings.pulp_host,
        settings.pulp_user,
        settings.pulp_password
    )
    build_tasks = await db.execute(
        select(models.BuildTask).where(
            models.BuildTask.id == task_id).options(
            selectinload(models.BuildTask.platform).selectinload(
                models.Platform.reference_platforms),
            selectinload(models.BuildTask.build).selectinload(
                models.Build.repos
            ),
            selectinload(models.BuildTask.rpm_module)
        )
    )
    build_task = build_tasks.scalars().first()
    module_index = None
    module_repo = None
    repositories = list(build_task.build.repos)
    if build_task.rpm_module:
        module_repo = next(
            build_repo for build_repo in repositories
            if build_repo.arch == build_task.arch
            and build_repo.debug is False
            and build_repo.type == 'rpm'
        )
        try:
            repo_modules_yaml = await pulp_client.get_repo_modules_yaml(
                module_repo.url)
            module_index = IndexWrapper.from_template(repo_modules_yaml)
        except Exception as e:
            message = f'Cannot parse modules index: {str(e)}'
            logging.exception('Cannot parse modules index: %s', str(e))
            raise ModuleUpdateError(message) from e
    rpm_artifacts = [item for item in task_artifacts if item.type == 'rpm']
    log_artifacts = [item for item in task_artifacts
                     if item.type == 'build_log']
    rpm_repositories = [repo for repo in repositories
                        if repo.type == 'rpm']
    log_repositories = [repo for repo in repositories
                        if repo.type == 'build_log']
    # Committing logs separately for UI to be able to fetch them
    logging.info('Processing logs')
    logs_entries = await __process_logs(
        pulp_client, build_task.id, log_artifacts, log_repositories)
    db.add_all(logs_entries)
    await db.commit()
    logging.info('Logs processing is finished')
    rpm_entries = await __process_rpms(
        pulp_client, build_task.id, build_task.arch,
        rpm_artifacts, rpm_repositories,
        built_srpm_url=build_task.built_srpm_url,
        module_index=module_index
    )
    if build_task.rpm_module and module_index:
        try:
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
        except Exception as e:
            message = f'Cannot update module information inside Pulp: {str(e)}'
            logging.exception('Cannot update module information inside Pulp: %s',
                              str(e))
            raise ModuleUpdateError(message) from e

    db.add_all(rpm_entries)
    db.add(build_task)
    await db.commit()
    await db.refresh(build_task)
    return build_task


async def __update_built_srpm_url(db: Session, build_task: models.BuildTask):
    uncompleted_tasks_ids = []
    if build_task.status in (BuildTaskStatus.COMPLETED,
                             BuildTaskStatus.FAILED):
        uncompleted_tasks_ids = await db.execute(
            select(models.BuildTask.id).where(
                models.BuildTask.id != build_task.id,
                models.BuildTask.ref_id == build_task.ref_id,
                models.BuildTask.status < BuildTaskStatus.COMPLETED,
            ),
        )
        uncompleted_tasks_ids = list(uncompleted_tasks_ids.scalars().all())

    # if SRPM isn't built in first arch of project,
    # we need to stop building project
    if build_task.status == BuildTaskStatus.FAILED and uncompleted_tasks_ids:
        update_query = update(models.BuildTask).where(
            models.BuildTask.id.in_(uncompleted_tasks_ids),
        ).values(status=BuildTaskStatus.FAILED)
        await db.execute(update_query)

        remove_query = delete(models.BuildTaskDependency).where(
            models.BuildTaskDependency.c.build_task_dependency.in_(
                uncompleted_tasks_ids),
        )
        await db.execute(remove_query)

    # if SRPM built we need to download them
    # from pulp repos in next tasks
    if all((build_task.status == BuildTaskStatus.COMPLETED,
            uncompleted_tasks_ids,
            build_task.built_srpm_url is None)):
        srpm_artifact = await db.execute(
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
        await db.execute(update_query)
        await db.execute(insert(models.BuildTaskArtifact), insert_values)

    await db.commit()


async def build_done(
            db: Session,
            request: build_node_schema.BuildDone
        ):
    try:
        build_task = await __process_build_task_artifacts(
            db, request.task_id, request.artifacts)
    except (ArtifactConversionError, ModuleUpdateError, RepositoryAddError) as e:
        update_query = update(models.BuildTask).where(
            models.BuildTask.id == request.task_id,
        ).values(status=BuildTaskStatus.FAILED)
        await db.execute(update_query)

        remove_query = delete(models.BuildTaskDependency).where(
            models.BuildTaskDependency.c.build_task_dependency == request.task_id,
        )
        await db.execute(remove_query)
        await db.commit()
        raise e

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
        build_task.arch == 'x86_64',
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
            logging.exception('Cannot process multilib packages: %s', str(e))
            raise MultilibProcessingError('Cannot process multilib packages')

    await db.execute(
        update(models.BuildTask).where(
            models.BuildTask.id == request.task_id).values(status=status)
    )

    try:
        await save_noarch_packages(db, build_task)
    except Exception as e:
        logging.exception('Cannot process noarch packages: %s', str(e))
        raise NoarchProcessingError('Cannot process noarch packages')

    await db.execute(
        delete(models.BuildTaskDependency).where(
            models.BuildTaskDependency.c.build_task_dependency == request.task_id
        )
    )

    rpms_result = await db.execute(select(models.BuildTaskArtifact).where(
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
        srpms = await db.execute(select(models.SourceRpm).where(
            models.SourceRpm.build_id == build_task.build_id))
        srpm = srpms.scalars().first()
    if srpm:
        if build_task.built_srpm_url is None:
            db.add(srpm)
            await db.commit()
            await db.refresh(srpm)
        for binary_rpm in binary_rpms:
            binary_rpm.source_rpm = srpm

    db.add_all(binary_rpms)
    await db.commit()

    try:
        await __update_built_srpm_url(db, build_task)
    except Exception as e:
        raise SrpmProvisionError(f'Cannot update subsequent tasks '
                                 f'with the source RPM link {str(e)}')

import asyncio
import datetime
import logging
import typing
import traceback

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
    RepositoryAddError,
)
from alws.schemas import build_node_schema
from alws.utils.modularity import IndexWrapper
from alws.utils.multilib import MultilibProcessor
from alws.utils.noarch import save_noarch_packages
from alws.utils.pulp_client import PulpClient
from alws.utils.rpm_package import get_rpm_package_info


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
                        models.Build.repos),
                    selectinload(models.BuildTask.build).selectinload(
                        models.Build.platform_flavors).selectinload(
                        models.PlatformFlavour.repos),
                    selectinload(models.BuildTask.rpm_module)
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
            task.ts = None
            if last_task is not None:
                await db.run_sync(add_build_task_dependencies, task, last_task)
            last_task = task
        await db.commit()


async def log_repo_exists(db: Session, task: models.BuildTask):
    repo = await db.execute(select(models.Repository).where(
        models.Repository.name == task.get_log_repo_name()
    ))
    return bool(repo.scalars().first())


async def create_build_log_repo(db: Session, task: models.BuildTask):
    pulp_client = PulpClient(
        settings.pulp_internal_host,
        settings.pulp_user,
        settings.pulp_password
    )
    repo_name = task.get_log_repo_name()
    pulp_repo = await pulp_client.get_log_repository(repo_name)
    if pulp_repo:
        pulp_href = pulp_repo['pulp_href']
        repo_url = (await pulp_client.get_log_distro(repo_name))['base_url']
    else:
        repo_url, pulp_href = await pulp_client.create_log_repo(repo_name)
    if await log_repo_exists(db, task):
        return
    log_repo = models.Repository(
        name=repo_name,
        url=repo_url,
        arch=task.arch,
        pulp_href=pulp_href,
        type='build_log',
        debug=False
    )
    db.add(log_repo)
    await db.flush()
    await db.refresh(log_repo)
    await db.execute(
        insert(models.BuildRepo).values(
            build_id=task.build_id,
            repository_id=log_repo.id
        )
    )
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


async def get_build_task(db: Session, task_id: int) -> models.BuildTask:
    build_tasks = await db.execute(
        select(models.BuildTask).where(models.BuildTask.id == task_id).options(
            selectinload(models.BuildTask.platform)
        )
    )
    return build_tasks.scalars().first()


async def __process_rpms(db: Session, pulp_client: PulpClient, task_id: int,
                         task_arch: str, task_artifacts: list,
                         repositories: list,
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
        if artifact.arch == 'src':
            if built_srpm_url is None:
                src_packages_tasks.append(pulp_client.create_entity(artifact))
        elif artifact.is_debuginfo:
            debug_packages_tasks.append(pulp_client.create_entity(artifact))
        else:
            arch_packages_tasks.append(pulp_client.create_entity(artifact))

    processed_packages = []
    for tasks, repo in (
                (src_packages_tasks, src_repo),
                (arch_packages_tasks, arch_repo),
                (debug_packages_tasks, debug_repo)
            ):
        if not tasks:
            continue
        try:
            results = await asyncio.gather(*tasks)
        except Exception as e:
            logging.exception(
                'Cannot create RPM packages for repo %s',
                str(repo)
            )
            raise ArtifactConversionError(
                f'Cannot put RPM packages into Pulp storage: {e}'
            )
        processed_packages.extend(results)
        hrefs = [item[0] for item in results]
        try:
            await pulp_client.modify_repository(
                repo.pulp_href, add=hrefs)
        except Exception:
            logging.exception(
                'Cannot add RPM packages to the repository: %s', str(repo)
            )
            raise RepositoryAddError(
                f'Cannot add RPM packages to the repository {str(repo)}'
            )

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
        pkg_fields = ['epoch', 'name', 'version', 'release', 'arch']
        results = await asyncio.gather(*(get_rpm_package_info(
            pulp_client, rpm.href, include_fields=pkg_fields)
            for rpm in rpms))
        packages_info = dict(results)
        srpm_info = None
        # we need to put source RPM in module as well, but it can be skipped
        # because it's built before
        if built_srpm_url is not None:
            task_query = select(models.BuildTask.build_id).where(
                models.BuildTask.id == task_id).scalar_subquery()
            srpm = next(
                item for item in task_artifacts if item.arch == 'src'
                and item.type == 'rpm'
            )
            srpm_query = select(models.SourceRpm).where(
                models.SourceRpm.build_id == task_query).options(
                selectinload(models.SourceRpm.artifact)
            )
            res = await db.execute(srpm_query)
            srpms = res.scalars().all()
            srpm_href = next(
                i.artifact.href for i in srpms if i.artifact.name == srpm.name
            )
            srpm_info = await pulp_client.get_rpm_package(
                srpm_href, include_fields=pkg_fields)
        try:
            for module in module_index.iter_modules():
                for rpm in rpms:
                    rpm_package = packages_info[rpm.href]
                    module.add_rpm_artifact(rpm_package)
                if srpm_info:
                    module.add_rpm_artifact(srpm_info)
        except Exception as e:
            raise ModuleUpdateError('Cannot update module: %s', str(e)) from e

    return rpms


async def __process_logs(pulp_client: PulpClient, task_id: int,
                         task_artifacts: list, repositories: list):
    if not repositories:
        logging.error('Log repository is absent, skipping logs processing')
        return
    logs = []
    str_task_id = str(task_id)
    repo = [repo for repo in repositories
            if repo.name.endswith(str_task_id)]
    if not repo:
        logging.error('Log repository is absent, skipping logs processing')
        return
    repo = repo[0]
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
        db: Session, pulp_client: PulpClient, task_id: int,
        task_artifacts: list,
        status: BuildTaskStatus):
    build_tasks = await db.execute(
        select(models.BuildTask).where(
            models.BuildTask.id == task_id).with_for_update().options(
            selectinload(models.BuildTask.platform).selectinload(
                models.Platform.reference_platforms),
            selectinload(models.BuildTask.rpm_module),
            selectinload(models.BuildTask.build).selectinload(
                models.Build.repos
            ),
        )
    )
    build_task = build_tasks.scalars().first()
    module_index = None
    module_repo = None
    query = select(models.Repository).join(models.BuildRepo).where(
        models.BuildRepo.c.build_id == build_task.build_id)
    repositories = list((await db.execute(query)).scalars().all())
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
    if logs_entries:
        db.add_all(logs_entries)
        await db.flush()
    logging.info('Logs processing is finished')
    rpm_entries = await __process_rpms(
        db, pulp_client, build_task.id, build_task.arch,
        rpm_artifacts, rpm_repositories,
        built_srpm_url=build_task.built_srpm_url,
        module_index=module_index
    )
    src_rpm = next((
        artifact.name for artifact in task_artifacts
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
        processor = MultilibProcessor(
            db, build_task, pulp_client=pulp_client, module_index=module_index)
        multilib_packages = await processor.get_packages(src_rpm)
        if module_index:
            multilib_module_artifacts = await processor.get_module_artifacts()
            await processor.add_multilib_module_artifacts(
                prepared_artifacts=multilib_module_artifacts)
            multilib_packages.update({
                i['name']: i['version'] for i in multilib_module_artifacts
            })
        await processor.add_multilib_packages(multilib_packages)
    if build_task.rpm_module and module_index:
        try:
            module_pulp_href, sha256 = await pulp_client.create_module(
                module_index.render(),
                build_task.rpm_module.name,
                build_task.rpm_module.stream,
                build_task.rpm_module.context,
                build_task.rpm_module.arch
            )
            old_modules = await pulp_client.get_repo_modules(module_repo.pulp_href)
            await pulp_client.modify_repository(
                module_repo.pulp_href,
                add=[module_pulp_href],
                remove=old_modules
            )
            build_task.rpm_module.sha256 = sha256
            build_task.rpm_module.pulp_href = module_pulp_href
        except Exception as e:
            message = f'Cannot update module information inside Pulp: {str(e)}'
            logging.exception(message)
            raise ModuleUpdateError(message) from e

    if rpm_entries:
        db.add_all(rpm_entries)
    db.add(build_task)
    await db.flush()
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
        uncompleted_tasks_ids = uncompleted_tasks_ids.scalars().all()

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
            {
                'build_task_id': task_id,
                'name': srpm_artifact.name,
                'type': 'rpm',
                'href': srpm_artifact.href
            }
            for task_id in uncompleted_tasks_ids
        ]

        update_query = update(models.BuildTask).where(
            models.BuildTask.ref_id == build_task.ref_id,
        ).values(built_srpm_url=srpm_url)
        await db.execute(update_query)
        await db.execute(insert(models.BuildTaskArtifact), insert_values)


async def safe_build_done(db: Session, request: build_node_schema.BuildDone):
    success = True
    pulp = PulpClient(
        settings.pulp_internal_host,
        settings.pulp_user,
        settings.pulp_password
    )
    try:
        async with db.begin():
            async with pulp.begin():
                await build_done(db, pulp, request)
    except Exception:
        logging.exception('Build done failed:')
        success = False
        update_query = update(models.BuildTask).where(
            models.BuildTask.id == request.task_id,
        ).values(status=BuildTaskStatus.FAILED, error=traceback.format_exc())
        await db.execute(update_query)
    finally:
        remove_dep_query = delete(models.BuildTaskDependency).where(
            models.BuildTaskDependency.c.build_task_dependency == request.task_id
        )
        await db.execute(remove_dep_query)
        await db.commit()
    return success


async def build_done(db: Session, pulp: PulpClient, request: build_node_schema.BuildDone):
    status = BuildTaskStatus.COMPLETED
    if request.status == 'failed':
        status = BuildTaskStatus.FAILED
    elif request.status == 'excluded':
        status = BuildTaskStatus.EXCLUDED

    build_task = await __process_build_task_artifacts(
        db, pulp, request.task_id, request.artifacts, status)

    await db.execute(
        update(models.BuildTask).where(
            models.BuildTask.id == request.task_id).values(status=status)
    )

    binary_rpms = await save_noarch_packages(db, pulp, build_task)

    rpms_result = await db.execute(select(models.BuildTaskArtifact).where(
        models.BuildTaskArtifact.build_task_id == build_task.id,
        models.BuildTaskArtifact.type == 'rpm'))
    srpm = None
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
            await db.flush()
            await db.refresh(srpm)
        for binary_rpm in binary_rpms:
            binary_rpm.source_rpm = srpm

    db.add_all(binary_rpms)
    await db.flush()
    await __update_built_srpm_url(db, build_task)

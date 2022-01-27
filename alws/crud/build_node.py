import datetime
import logging
import typing

import sqlalchemy
from sqlalchemy import delete, update
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
            selectinload(models.BuildTask.build).selectinload(
                models.Build.repos
            ),
            selectinload(models.BuildTask.rpm_module)
        ).with_for_update()
    )
    build_task = build_tasks.scalars().first()
    module_index = None
    module_repo = None
    artifacts = []
    str_task_id = str(task_id)
    if build_task.rpm_module:
        module_repo = next(
            build_repo for build_repo in build_task.build.repos
            if build_repo.arch == build_task.arch
            and not build_repo.debug
            and build_repo.type == 'rpm'
        )
        repo_modules_yaml = await pulp_client.get_repo_modules_yaml(
            module_repo.url)
        module_index = IndexWrapper.from_template(repo_modules_yaml)
    for artifact in task_artifacts:
        href = None
        arch = build_task.arch
        if artifact.type == 'rpm' and artifact.arch == 'src':
            arch = artifact.arch
        repos = list(
            build_repo for build_repo in build_task.build.repos
            if build_repo.arch == arch
            and build_repo.type == artifact.type
            and build_repo.debug == artifact.is_debuginfo
        )
        if artifact.type == 'rpm':
            repo = repos[0]
            href = await pulp_client.create_rpm_package(
                artifact.name, artifact.href, repo.pulp_href)
            if module_index:
                for module in module_index.iter_modules():
                    rpm_package = await pulp_client.get_rpm_package(href)
                    module.add_rpm_artifact(rpm_package)
        elif artifact.type == 'build_log':
            repo = next(
                repo for repo in repos
                if repo.name.endswith(str_task_id)
            )
            href = await pulp_client.create_file(
                artifact.name, artifact.href, repo.pulp_href)
        if not href:
            logging.error("Artifact %s was not saved properly in Pulp, "
                          "skipping", str(artifact))
            continue
        artifacts.append(
            models.BuildTaskArtifact(
                build_task_id=build_task.id,
                name=artifact.name,
                type=artifact.type,
                href=href
            )
        )
    if build_task.rpm_module:
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

    db.add_all(artifacts)
    db.add(build_task)
    await db.commit()
    await db.refresh(build_task)
    return build_task


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

    multilib_conditions = (
        build_task.arch in ('x86_64', 'i686'),
        status == BuildTaskStatus.COMPLETED,
        bool(settings.beholder_host),
        # TODO: Beholder doesn't have authorization right now
        # bool(settings.beholder_token),
    )
    if all(multilib_conditions):
        src_rpm = next(
            artifact.name for artifact in request.artifacts
            if artifact.arch == 'src' and artifact.type == 'rpm'
        )
        multilib_pkgs = await get_multilib_packages(db, build_task, src_rpm)
        if multilib_pkgs:
            await add_multilib_packages(db, build_task, multilib_pkgs)
    await save_noarch_packages(db, build_task)

    await db.execute(
        update(models.BuildTask).where(
            models.BuildTask.id == request.task_id).values(status=status)
    )

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
        if rpm.name.endswith('.src.rpm'):
            srpm = models.SourceRpm()
            srpm.artifact = rpm
            srpm.build = build_task.build
        else:
            binary_rpm = models.BinaryRpm()
            binary_rpm.artifact = rpm
            binary_rpm.build = build_task.build
            binary_rpms.append(binary_rpm)
    if srpm:
        db.add(srpm)
        await db.commit()
        await db.refresh(srpm)
        for binary_rpm in binary_rpms:
            binary_rpm.source_rpm = srpm

    db.add_all(binary_rpms)
    await db.commit()

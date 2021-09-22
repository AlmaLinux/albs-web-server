import typing
import datetime

import sqlalchemy
from sqlalchemy import update, delete
from sqlalchemy.future import select
from sqlalchemy.orm import Session, selectinload
from sqlalchemy.sql.expression import func

from alws import models
from alws.errors import DataNotFoundError, BuildError
from alws.config import settings
from alws.utils.pulp_client import PulpClient
from alws.utils.github import get_user_github_token, get_github_user_info
from alws.utils.jwt_utils import generate_JWT_token
from alws.constants import BuildTaskStatus
from alws.build_planner import BuildPlanner
from alws.schemas import (
    build_schema, user_schema, platform_schema, build_node_schema,
    distro_schema
)
from alws.utils.distro_utils import create_empty_repo
from fastapi import HTTPException, status


__all__ = ['create_build', 'get_builds', 'create_platform', 'get_platforms']


async def create_build(
            db: Session,
            build: build_schema.BuildCreate,
            user_id: int
        ) -> models.Build:
    async with db.begin():
        planner = BuildPlanner(db, user_id, build.platforms)
        await planner.load_platforms()
        for task in build.tasks:
            await planner.add_task(task)
        if build.linked_builds:
            for linked_id in build.linked_builds:
                linked_build = await get_builds(db, linked_id)
                if linked_build:
                    await planner.add_linked_builds(linked_build)
        db_build = planner.create_build()
        db.add(db_build)
        await db.flush()
        await db.refresh(db_build)
        await planner.init_build_repos()
        await db.commit()
    # TODO: this is ugly hack for now
    return await get_builds(db, db_build.id)


async def get_builds(
            db: Session,
            build_id: typing.Optional[int] = None,
            page_number: typing.Optional[int] = None
        ) -> typing.Union[typing.List[models.Build], dict]:
    query = select(models.Build).order_by(models.Build.id.desc()).options(
        selectinload(models.Build.tasks).selectinload(
            models.BuildTask.platform),
        selectinload(models.Build.tasks).selectinload(models.BuildTask.ref),
        selectinload(models.Build.user),
        selectinload(models.Build.tasks).selectinload(
            models.BuildTask.artifacts),
        selectinload(models.Build.linked_builds)
    )
    if page_number:
        query = query.slice(10 * page_number - 10, 10 * page_number)
    if build_id is not None:
        query = query.where(models.Build.id == build_id)
    result = await db.execute(query)
    if build_id:
        return result.scalars().first()
    elif page_number:
        total_builds = await db.execute(func.count(models.Build.id))
        total_builds = total_builds.scalar()
        return {'builds': result.scalars().all(),
                'total_builds': total_builds,
                'current_page': page_number}
    return result.scalars().all()


async def modify_platform(
            db: Session,
            platform: platform_schema.PlatformModify
        ) -> models.Platform:
    query = models.Platform.name == platform.name
    async with db.begin():
        db_platform = await db.execute(
            select(models.Platform).where(query).options(
                selectinload(models.Platform.repos)
            ).with_for_update()
        )
        db_platform = db_platform.scalars().first()
        if not db_platform:
            raise DataNotFoundError(
                f'Platform with name: "{platform.name}" does not exists'
            )
        for key in ('type', 'distr_type', 'distr_version', 'arch_list',
                    'data'):
            value = getattr(platform, key, None)
            if value is not None:
                setattr(db_platform, key, value)
        db_repos = {repo.name: repo for repo in db_platform.repos}
        new_repos = {repo.name: repo for repo in platform.repos}
        for repo in platform.repos:
            if repo.name in db_repos:
                db_repo = db_repos[repo.name]
                for key in repo.dict().keys():
                    setattr(db_repo, key, getattr(repo, key))
            else:
                db_platform.repos.append(models.Repository(**repo.dict()))
        to_remove = []
        for repo_name in db_repos:
            if repo_name not in new_repos:
                to_remove.append(repo_name)
        remove_query = models.Repository.name.in_(to_remove)
        await db.execute(
            delete(models.BuildTaskDependency).where(remove_query)
        )
        await db.commit()
    await db.refresh(db_platform)
    return db_platform


async def create_platform(
            db: Session,
            platform: platform_schema.PlatformCreate
        ) -> models.Platform:
    db_platform = models.Platform(
        name=platform.name,
        type=platform.type,
        distr_type=platform.distr_type,
        distr_version=platform.distr_version,
        data=platform.data,
        arch_list=platform.arch_list
    )
    for repo in platform.repos:
        db_platform.repos.append(models.Repository(**repo.dict()))
    db.add(db_platform)
    await db.commit()
    await db.refresh(db_platform)
    return db_platform


async def create_distro(
        db: Session,
        distribution: distro_schema.DistroCreate
) -> models.Distribution:

    db_distro = await db.execute(select(models.Distribution).where(
        models.Distribution.name.__eq__(distribution.name)))
    db_distro = db_distro.scalars().first()

    if db_distro:
        error_msg = f'{distribution.name} distribution already exists'
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                            detail=error_msg)
    else:
        distro_platforms = await db.execute(select(models.Platform).where(
            models.Platform.name.in_(distribution.platforms)))
        distro_platforms = distro_platforms.scalars().all()

        db_distribution = models.Distribution(
            name=distribution.name
        )
        for platform in distro_platforms:
            db_distribution.platforms.append(platform)

        pulp_client = PulpClient(
            settings.pulp_host,
            settings.pulp_user,
            settings.pulp_password
        )
        await create_empty_repo(pulp_client, db_distribution)
        db.add(db_distribution)
        await db.commit()
        await db.refresh(db_distribution)
        return db_distribution


async def get_platforms(db):
    db_platforms = await db.execute(select(models.Platform))
    return db_platforms.scalars().all()


async def get_distributions(db):
    db_distros = await db.execute(select(models.Distribution))
    return db_distros.scalars().all()


async def modify_distribution(build_id: int, distribution: str, db: Session,
                              modification: str):

    db_distro = await db.execute(select(models.Distribution).where(
        models.Distribution.name.__eq__(distribution)
    ).options(selectinload(models.Distribution.repositories),
              selectinload(models.Distribution.packages)).with_for_update())
    db_distro = db_distro.scalars().first()

    db_build_tasks = await db.execute(select(models.BuildTask).where(
        models.BuildTask.build_id.__eq__(build_id)
    ).options(selectinload(models.BuildTask.artifacts)))
    db_build_tasks = db_build_tasks.scalars().all()

    pulp_client = PulpClient(settings.pulp_host, settings.pulp_user,
                             settings.pulp_password)

    db_build = await db.execute(select(models.Build).where(
        models.Build.id.__eq__(build_id)))
    db_build = db_build.scalars().first()

    if modification == 'add':
        if db_build in db_distro.packages:
            error_msg = f'Packages of build {build_id} have already been' \
                        f' added to {distribution} distribution'
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=error_msg)
        else:
            db_distro.packages.append(db_build)
    if modification == 'remove':
        if db_build not in db_distro.packages:
            error_msg = f'Packages of build {build_id} cannot be removed ' \
                        f'from {distribution} distribution ' \
                        f'as they are not added there'
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                                detail=error_msg)
        else:
            remove_query = models.Build.id.__eq__(build_id)
            await db.execute(
                delete(models.DistributionPackages).where(remove_query)
            )
    await db.commit()
    await db.refresh(db_distro)
    for task in db_build_tasks:
        for artifact in task.artifacts:
            if artifact.type == 'rpm':
                for distro_repo in db_distro.repositories:
                    if distro_repo.arch in artifact.name:
                        res = await pulp_client.modify_repository(
                            repo_from=artifact.href,
                            repo_to=distro_repo.pulp_href,
                            content=f'{modification}_content_units')
                        if res.get('task', None):
                            continue
                        else:
                            error_msg = 'Could not add packages to distribution'
                            raise HTTPException(
                                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                                detail=error_msg)
    return True


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


async def ping_tasks(
            db: Session,
            task_list: typing.List[int]
        ):
    query = models.BuildTask.id.in_(task_list)
    now = datetime.datetime.now()
    async with db.begin():
        await db.execute(update(models.BuildTask).where(query).values(ts=now))
        await db.commit()


async def build_done(
            db: Session,
            request: build_node_schema.BuildDone
        ):
    async with db.begin():
        query = models.BuildTask.id == request.task_id
        build_task = await db.execute(
            select(models.BuildTask).where(query).options(
                selectinload(models.BuildTask.build).selectinload(
                    models.Build.repos
                )
            ).with_for_update()
        )
        build_task = build_task.scalars().first()
        if BuildTaskStatus.is_finished(build_task.status):
            raise BuildError(f'Build task {build_task.id} already completed')
        status = BuildTaskStatus.COMPLETED
        if request.status == 'failed':
            status = BuildTaskStatus.FAILED
        elif request.status == 'excluded':
            status = BuildTaskStatus.EXCLUDED
        build_task.status = status
        remove_query = (
            models.BuildTaskDependency.c.build_task_dependency == request.task_id
        )
        await db.execute(
            delete(models.BuildTaskDependency).where(remove_query)
        )
        pulp_client = PulpClient(
            settings.pulp_host,
            settings.pulp_user,
            settings.pulp_password
        )
        artifacts = []
        for artifact in request.artifacts:
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
            elif artifact.type == 'build_log':
                repo = next(
                    repo for repo in repos
                    if repo.name.endswith(str(request.task_id))
                )
                href = await pulp_client.create_file(
                    artifact.name, artifact.href, repo.pulp_href)
            artifacts.append(
                models.BuildTaskArtifact(
                    build_task_id=build_task.id,
                    name=artifact.name,
                    type=artifact.type,
                    href=href
                )
            )
        db.add_all(artifacts)


async def github_login(
            db: Session,
            user: user_schema.LoginGithub
        ) -> models.User:
    async with db.begin():
        github_user_token = await get_user_github_token(
            user.code,
            settings.github_client,
            settings.github_client_secret
        )
        github_info = await get_github_user_info(github_user_token)
        if not any(item for item in github_info['organizations']
                   if item['login'] == 'AlmaLinux'):
            return
        new_user = models.User(
            username=github_info['login'],
            email=github_info['email']
        )
        query = models.User.username == new_user.username
        db_user = await db.execute(select(models.User).where(
            query).with_for_update())
        db_user = db_user.scalars().first()
        if not db_user:
            db.add(new_user)
            db_user = new_user
            await db.flush()
        db_user.github_token = github_user_token
        db_user.jwt_token = generate_JWT_token(
            {'user_id': db_user.id},
            settings.jwt_secret,
            settings.jwt_algorithm
        )
        await db.commit()
    await db.refresh(db_user)
    return db_user


async def get_user(
            db: Session,
            user_id: typing.Optional[int] = None,
            user_name: typing.Optional[str] = None,
            user_email: typing.Optional[str] = None
        ) -> models.User:
    query = models.User.id == user_id
    if user_name is not None:
        query = models.User.name == user_name
    elif user_email is not None:
        query = models.User.email == user_email
    db_user = await db.execute(select(models.User).where(query))
    return db_user.scalars().first()

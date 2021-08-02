import typing
import datetime

import sqlalchemy
from sqlalchemy import update, delete
from sqlalchemy.future import select
from sqlalchemy.orm import Session, selectinload

from alws import models
from alws.config import settings
from alws.utils.pulp_client import PulpClient
from alws.utils.github import get_user_github_token, get_github_user_info
from alws.utils.jwt_utils import generate_JWT_token
from alws.constants import BuildTaskStatus
from alws.build_planner import BuildPlanner
from alws.schemas import (
    build_schema, user_schema, platform_schema, build_node_schema
)


__all__ = ['create_build', 'get_build', 'create_platform', 'get_platforms']


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
        db_build = planner.create_build()
        db.add(db_build)
        await db.flush()
        await db.refresh(db_build)
        await planner.init_build_repos()
        await db.commit()
    # TODO: this is ugly hack for now
    return await get_build(db, db_build.id)


async def get_build(db: Session, build_id: int) -> models.Build:
    query = models.Build.id == build_id
    result = await db.execute(
        select(models.Build).where(query).options(
            selectinload(models.Build.tasks).selectinload(
                models.BuildTask.platform),
            selectinload(models.Build.tasks).selectinload(
                models.BuildTask.ref),
            selectinload(models.Build.user)
        )
    )
    return result.scalars().first()


async def get_builds(db: Session) -> typing.List[models.Build]:
    result = await db.execute(
        select(models.Build).order_by(models.Build.id.desc()).options(
            selectinload(models.Build.tasks).selectinload(
                models.BuildTask.platform),
            selectinload(models.Build.tasks).selectinload(models.BuildTask.ref),
            selectinload(models.Build.user)
        )
    )
    return result.scalars().all()


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


async def get_platforms(db):
    db_platforms = await db.execute(select(models.Platform))
    return db_platforms.scalars().all()


async def get_available_build_task(
            db: Session
        ) -> models.BuildTask:
    async with db.begin():
        # TODO: here should be config value
        ts_expired = datetime.datetime.now() - datetime.timedelta(minutes=20)
        query = ~models.BuildTask.dependencies.any()
        db_task = await db.execute(
            select(models.BuildTask).where(query).with_for_update().filter(
                    sqlalchemy.and_(
                        models.BuildTask.status < BuildTaskStatus.COMPLETED,
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
                    models.Build.user)
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
    await db.execute(update(models.BuildTask).where(query).values(ts=now))


async def build_done(
            db: Session,
            request: build_node_schema.BuildDone
        ):
    async with db.begin():
        status = BuildTaskStatus.COMPLETED
        if not request.success:
            status = BuildTaskStatus.FAILED
        query = models.BuildTask.id == request.task_id
        build_task = await db.execute(select(models.BuildTask).where(
            query).with_for_update())
        build_task = build_task.scalars().first()
        build_task.status = status
        remove_query = (
            models.BuildTaskDependency.c.build_task_dependency == request.task_id
        )
        await db.execute(
            delete(models.BuildTaskDependency).where(remove_query)
        )

        build_query = models.Build.id == build_task.build_id
        build = await db.execute(
            select(models.Build).where(build_query).options(
                selectinload(models.Build.repos)
            )
        )
        build = build.scalars().first()
        pulp_client = PulpClient(
            settings.pulp_host,
            settings.pulp_user,
            settings.pulp_password
        )
        for artifact in request.artifacts:
            repo = next(build_repo for build_repo in build.repos
                        if build_repo.arch == artifact.arch)
            await pulp_client.create_rpm_package(
                artifact.name, artifact.pulp_href, repo.pulp_href)


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

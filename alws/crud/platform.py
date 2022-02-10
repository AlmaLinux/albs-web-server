import typing

from sqlalchemy import and_, delete
from sqlalchemy.future import select
from sqlalchemy.orm import Session, selectinload

from alws import models
from alws.errors import DataNotFoundError
from alws.schemas import platform_schema


async def modify_platform(
            db: Session,
            platform: platform_schema.PlatformModify
        ) -> typing.Union[models.Platform, models.ReferencePlatform]:
    query = models.Platform.name == platform.name
    async with db.begin():
        if platform.is_reference:
            query = and_(
                models.ReferencePlatform.name == platform.name,
                models.ReferencePlatform.distr_version == platform.distr_version)
            db_platform = await db.execute(
                select(models.Platform).where(query))
        else:
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
        platform_fields = ('type', 'distr_type', 'distr_version', 'arch_list',
                           'data', 'modularity', 'reference_platform')
        for key in platform_fields:
            value = getattr(platform, key, None)
            if value is not None:
                setattr(db_platform, key, value)
        db_repos = {}
        if not platform.is_reference:
            db_repos = {repo.name: repo for repo in db_platform.repos}
        payload_repos = getattr(platform, 'repos', None)
        new_repos = {}
        if payload_repos:
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
            if new_repos and repo_name not in new_repos:
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
        ) -> typing.Union[models.Platform, models.ReferencePlatform]:
    if platform.is_reference:
        db_platform = models.ReferencePlatform(
            name=platform.name,
            type=platform.type,
            distr_type=platform.distr_type,
            distr_version=platform.distr_version,
            arch_list=platform.arch_list,
        )
    else:
        db_platform = models.Platform(
            name=platform.name,
            type=platform.type,
            distr_type=platform.distr_type,
            distr_version=platform.distr_version,
            test_dist_name=platform.test_dist_name,
            data=platform.data,
            arch_list=platform.arch_list,
            modularity=platform.modularity
        )
    if platform.repos:
        for repo in platform.repos:
            db_platform.repos.append(models.Repository(**repo.dict()))
    db.add(db_platform)
    await db.commit()
    await db.refresh(db_platform)
    return db_platform


async def get_platforms(
            db: Session,
            is_reference: bool = False,
        ) -> typing.List[typing.Union[models.Platform,
                                      models.ReferencePlatform]]:
    query = select(models.Platform)
    if is_reference:
        query = select(models.ReferencePlatform)
    db_platforms = await db.execute(query)
    return db_platforms.scalars().all()


async def get_platform(
            db: Session,
            name: str,
            is_reference: bool = False,
        ) -> typing.Union[models.Platform, models.ReferencePlatform]:
    query = select(models.Platform).where(models.Platform.name == name)
    if is_reference:
        query = select(models.ReferencePlatform).where(
            models.ReferencePlatform.name == name)
    db_platform = await db.execute(query)
    return db_platform.scalars().first()

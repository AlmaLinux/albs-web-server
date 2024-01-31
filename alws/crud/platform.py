import typing

from sqlalchemy import and_, delete
from sqlalchemy.future import select
from sqlalchemy.orm import Session, selectinload

from alws import models
from alws.errors import DataNotFoundError
from alws.schemas import platform_schema


async def modify_platform(
    db: Session, platform: platform_schema.PlatformModify
) -> models.Platform:
    query = models.Platform.name == platform.name
    async with db.begin():
        db_platform = await db.execute(
            select(models.Platform)
            .where(query)
            .options(
                selectinload(models.Platform.repos),
                selectinload(models.Platform.reference_platforms),
            )
            .with_for_update()
        )
        db_platform = db_platform.scalars().first()
        if not db_platform:
            raise DataNotFoundError(
                f'Platform with name: "{platform.name}" does not exists'
            )
        fields_to_update = (
            'type',
            'distr_type',
            'distr_version',
            'arch_list',
            'data',
            'modularity',
            'is_reference',
            'weak_arch_list',
            'copy_priority_arches',
            'copyright',
            'contact_mail',
        )
        for field in fields_to_update:
            value = getattr(platform, field, None)
            if value is not None:
                setattr(db_platform, field, value)
        db_repos = {repo.name: repo for repo in db_platform.repos}
        payload_repos = getattr(platform, 'repos', None)
        new_repos = {}
        if payload_repos:
            new_repos = {repo.name: repo for repo in platform.repos}
            for repo in platform.repos:
                if repo.name in db_repos:
                    db_repo = db_repos[repo.name]
                    for key in repo.model_dump().keys():
                        setattr(db_repo, key, getattr(repo, key))
                else:
                    db_platform.repos.append(
                        models.Repository(**repo.model_dump())
                    )

        ref_platform_ids_to_remove = [
            ref_platform.id
            for ref_platform in db_platform.reference_platforms
            if ref_platform.name not in platform.reference_platforms
        ]
        ref_platforms = await db.execute(
            select(models.Platform).where(
                models.Platform.name.in_(platform.reference_platforms)
            )
        )
        for ref_platform in ref_platforms.scalars().all():
            db_platform.reference_platforms.append(ref_platform)

        await db.execute(
            delete(models.ReferencePlatforms).where(
                and_(
                    models.ReferencePlatforms.c.platform_id == db_platform.id,
                    models.ReferencePlatforms.c.refefence_platform_id.in_(
                        ref_platform_ids_to_remove
                    ),
                )
            )
        )

        repos_to_remove = []
        for repo_name in db_repos:
            if new_repos and repo_name not in new_repos:
                repos_to_remove.append(repo_name)
        remove_query = models.Repository.name.in_(repos_to_remove)
        await db.execute(delete(models.Repository).where(remove_query))
        await db.commit()
    await db.refresh(db_platform)
    return db_platform


async def create_platform(
    db: Session, platform: platform_schema.PlatformCreate
) -> models.Platform:
    db_platform = models.Platform(
        name=platform.name,
        contact_mail=platform.contact_mail,
        copyright=platform.copyright,
        type=platform.type,
        distr_type=platform.distr_type,
        distr_version=platform.distr_version,
        test_dist_name=platform.test_dist_name,
        data=platform.data,
        arch_list=platform.arch_list,
        is_reference=platform.is_reference,
        modularity=platform.modularity,
        weak_arch_list=platform.weak_arch_list,
    )
    if platform.repos:
        for repo in platform.repos:
            db_platform.repos.append(models.Repository(**repo.model_dump()))
    db.add(db_platform)
    await db.commit()
    await db.refresh(db_platform)
    return db_platform


async def get_platforms(
    db: Session,
    is_reference: bool = False,
) -> typing.List[models.Platform]:
    condition = models.Platform.is_reference.is_(is_reference)
    db_platforms = await db.execute(select(models.Platform).where(condition))
    return db_platforms.scalars().all()


async def get_platform(db: Session, name: str) -> models.Platform:
    db_platform = await db.execute(
        select(models.Platform).where(models.Platform.name == name)
    )
    return db_platform.scalars().first()

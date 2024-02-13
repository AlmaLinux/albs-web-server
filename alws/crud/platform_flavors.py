from typing import List

import sqlalchemy
from sqlalchemy import delete
from sqlalchemy.future import select
from sqlalchemy.orm import selectinload

from alws import models
from alws.schemas.platform_flavors_schema import CreateFlavour, UpdateFlavour


async def delete_flavour(db, pf_id: int) -> models.PlatformFlavour:
    repos_to_delete = (
        (
            await db.execute(
                select(models.FlavourRepo.c.repository_id).where(
                    models.FlavourRepo.c.flavour_id == pf_id
                )
            )
        )
        .scalars()
        .all()
    )

    await db.execute(
        delete(models.FlavourRepo).where(
            models.FlavourRepo.c.flavour_id == pf_id
        )
    )

    await db.execute(
        delete(models.Repository).where(
            models.Repository.id.in_(repos_to_delete)
        )
    )

    await db.execute(
        delete(models.PlatformFlavour).where(
            models.PlatformFlavour.id == pf_id
        )
    )
    await db.commit()


async def create_flavour(db, flavour: CreateFlavour) -> models.PlatformFlavour:
    db_flavour = models.PlatformFlavour(
        name=flavour.name,
        modularity=flavour.modularity,
        data=flavour.data,
    )
    for repo in flavour.repositories:
        db_repo = await db.execute(
            select(models.Repository).where(
                sqlalchemy.and_(
                    models.Repository.name == repo.name,
                    models.Repository.arch == repo.arch,
                    models.Repository.type == repo.type,
                    models.Repository.debug == repo.debug,
                )
            )
        )
        db_repo = db_repo.scalars().first()
        if not db_repo:
            db_repo = models.Repository(**repo.model_dump())
            db.add(db_repo)
        db_flavour.repos.append(db_repo)
    db.add(db_flavour)
    await db.commit()
    db_flavour = await db.execute(
        select(models.PlatformFlavour)
        .where(models.PlatformFlavour.name == flavour.name)
        .options(selectinload(models.PlatformFlavour.repos))
    )
    return db_flavour.scalars().all()


async def update_flavour(db, flavour: UpdateFlavour) -> models.PlatformFlavour:
    db_flavour = await find_flavour_by_name(db, flavour.name)
    if not db_flavour:
        return
    for key in ("name", "modularity", "data"):
        if getattr(flavour, key):
            setattr(db_flavour, key, getattr(flavour, key))
    for repo in flavour.repositories:
        db_repo = await db.execute(
            select(models.Repository).where(
                sqlalchemy.and_(
                    models.Repository.name == repo.name,
                    models.Repository.arch == repo.arch,
                    models.Repository.type == repo.type,
                    models.Repository.debug == repo.debug,
                )
            )
        )
        db_repo = db_repo.scalars().first()
        if not db_repo:
            db_repo = models.Repository(**repo.model_dump())
            db.add(db_repo)
        db_flavour.repos.append(db_repo)
    db.add(db_flavour)
    await db.commit()
    return await find_flavour_by_name(db, flavour.name)


async def list_flavours(
    db, ids: List[int] = None
) -> List[models.PlatformFlavour]:
    query = select(models.PlatformFlavour).options(
        selectinload(models.PlatformFlavour.repos)
    )
    if ids is not None:
        query = query.where(models.PlatformFlavour.id.in_(ids))
    flavors = await db.execute(query)
    return flavors.scalars().all()


async def find_flavour_by_name(db, flavour_name: str):
    db_flavour = await db.execute(
        select(models.PlatformFlavour)
        .where(models.PlatformFlavour.name == flavour_name)
        .options(selectinload(models.PlatformFlavour.repos))
    )
    return db_flavour.scalars().first()

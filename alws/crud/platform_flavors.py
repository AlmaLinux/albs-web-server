from typing import List

import sqlalchemy
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.orm import selectinload

from alws import models
from alws.schemas.platform_flavors_schema import CreateFlavour, UpdateFlavour


async def create_flavour(db: AsyncSession,
                         flavour: CreateFlavour) -> models.PlatformFlavour:
    db_flavour = models.PlatformFlavour(name=flavour.name,
                                        modularity=flavour.modularity)
    for repo in flavour.repositories:
        db_repo = await db.execute(select(models.Repository).where(
            sqlalchemy.and_(
                models.Repository.name == repo.name,
                models.Repository.arch == repo.arch,
                models.Repository.type == repo.type,
                models.Repository.debug == repo.debug,
            )
        ))
        db_repo = db_repo.scalars().first()
        if not db_repo:
            db_repo = models.Repository(**repo.dict())
            db.add(db_repo)
        db_flavour.repos.append(db_repo)
    db.add(db_flavour)
    await db.flush()
    db_flavour = await db.execute(select(models.PlatformFlavour).where(
        models.PlatformFlavour.name == flavour.name
    ).options(selectinload(models.PlatformFlavour.repos)))
    return db_flavour.scalars().all()


async def update_flavour(db: AsyncSession,
                         flavour: UpdateFlavour) -> models.PlatformFlavour:
    db_flavour = await find_flavour_by_id(db, flavour.id)
    for key in ('name', 'modularity'):
        if getattr(flavour, key):
            setattr(db_flavour, key, getattr(flavour, key))
    await db.flush()
    return await find_flavour_by_id(db, flavour.id)


async def list_flavours(db: AsyncSession,
                        ids: List[int] = None) -> List[models.PlatformFlavour]:
    query = select(models.PlatformFlavour).options(
        selectinload(models.PlatformFlavour.repos)
    )
    if ids is not None:
        query = query.where(models.PlatformFlavour.id.in_(ids))
    flavors = await db.execute(query)
    return flavors.scalars().all()


async def find_flavour_by_id(db: AsyncSession, flavour_id: int):
    db_flavour = await db.execute(select(models.PlatformFlavour).where(
        models.PlatformFlavour.id == flavour_id
    ).options(selectinload(models.PlatformFlavour.repos)))
    return db_flavour.scalars().first()

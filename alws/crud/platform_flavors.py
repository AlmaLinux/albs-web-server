from typing import List

import sqlalchemy
from sqlalchemy.future import select
from sqlalchemy.orm import selectinload

from alws import models
from alws.schemas.platform_flavors_schema import CreateFlavour


async def create_flavour(db, flavour: CreateFlavour) -> models.PlatformFlavour:
    db_flavour = models.PlatformFlavour(name=flavour.name)
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
    await db.commit()
    db_flavour = await db.execute(select(models.PlatformFlavour).where(
        models.PlatformFlavour.name == flavour.name
    ).options(selectinload(models.PlatformFlavour.repos)))
    return db_flavour.scalars().all()


async def list_flavours(db) -> List[models.PlatformFlavour]:
    flavours = await db.execute(select(models.PlatformFlavour).options(
        selectinload(models.PlatformFlavour.repos)
    ))
    return flavours.scalars().all()
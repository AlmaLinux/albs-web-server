from typing import List

import sqlalchemy
from sqlalchemy.future import select
from sqlalchemy.orm import selectinload

from alws import models
from alws.schemas.platform_flavors_schema import CreateFlavour


async def create_flavour(db, flavour: CreateFlavour) -> models.PlatformFlavour:
    flavour = models.PlatformFlavour(name=flavour.name)
    for repo in flavour.repos:
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
        flavour.append(db_repo)
    db.add(flavour)
    await db.commit()
    await db.refresh(flavour)
    return flavour


async def list_flavours(db) -> List[models.PlatformFlavour]:
    flavours = await db.execute(select(models.PlatformFlavour).options(
        selectinload(models.PlatformFlavour.repos)
    ))
    return flavours.scalars().all()
import typing

from sqlalchemy.future import select
from sqlalchemy.orm import selectinload

from alws import models
from alws.database import Session


__all__ = ['get_roles']


async def get_roles(db: Session) -> typing.List[models.UserRole]:
    return (await db.execute(select(models.UserRole))).scalars().all()

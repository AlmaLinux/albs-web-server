import typing

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from alws import models


__all__ = ['get_roles']


async def get_roles(db: AsyncSession) -> typing.List[models.UserRole]:
    return (await db.execute(select(models.UserRole))).scalars().all()

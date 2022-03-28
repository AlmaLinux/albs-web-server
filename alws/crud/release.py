import typing

from sqlalchemy.future import select
from sqlalchemy.orm import Session, selectinload

from alws import models


async def get_releases(db: Session) -> typing.List[models.Release]:
    release_result = await db.execute(select(models.Release).options(
        selectinload(models.Release.created_by),
        selectinload(models.Release.platform),
    ).order_by(models.Release.id))
    return release_result.scalars().all()

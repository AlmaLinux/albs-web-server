import typing

from sqlalchemy.future import select
from sqlalchemy.orm import Session, selectinload

from alws import models


async def get_releases(page_number: typing.Optional[int],
                       db: Session
) -> typing.List[models.Release]:
    release_result = await db.execute(select(models.Release).options(
        selectinload(models.Release.created_by),
        selectinload(models.Release.platform),
    ).order_by(models.Release.id))
    releases = release_result.scalars().all()
    if page_number:
        releases = releases[10 * page_number - 10 : 10 * page_number]
    return releases

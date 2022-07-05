import typing

from sqlalchemy.future import select
from sqlalchemy.orm import Session, selectinload
from sqlalchemy.sql.expression import func

from alws import models


async def get_releases(page_number: typing.Optional[int],
                       db: Session
) -> typing.List[models.Release]:
    query = select(models.Release).options(
        selectinload(models.Release.owner),
        selectinload(models.Release.platform),
    ).order_by(models.Release.id.desc())
    if page_number:
        query = query.slice(10 * page_number - 10, 10 * page_number)
    release_result = await db.execute(query)
    if page_number:
        total_releases = await db.execute(func.count(models.Release.id))
        total_releases = total_releases.scalar()
        return {'releases': release_result.scalars().all(),
                'total_releases': total_releases,
                'current_page': page_number}
    return release_result.scalars().all()

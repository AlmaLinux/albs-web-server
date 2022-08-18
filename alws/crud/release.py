import typing

from sqlalchemy.future import select
from sqlalchemy.orm import Session, selectinload
from sqlalchemy.sql.expression import func

from alws import models
from alws.errors import ProductError
from alws.schemas import release_schema
from alws.release_planner import get_releaser_class


__all__ = [
    'get_releases',
    'create_release',
    'commit_release',
    'update_release',
]


async def get_releases(
        page_number: typing.Optional[int],
        db: Session
) -> typing.List[models.Release]:
    query = select(models.Release).options(
        selectinload(models.Release.owner),
        selectinload(models.Release.platform),
        selectinload(models.Release.product),
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


async def __get_product(db: Session, product_id: int) -> models.Product:
    product = (await db.execute(select(models.Product).where(
        models.Product.id == product_id))).scalars().first()
    if not product:
        raise ProductError(f'Product with ID {product_id} not found')
    return product


async def create_release(
        db: Session,
        user_id: int,
        payload: release_schema.ReleaseCreate,
) -> models.Release:
    product = await __get_product(db, payload.product_id)
    releaser = get_releaser_class(product)(db)
    return await releaser.create_new_release(user_id, payload)


async def update_release(
        db: Session,
        release_id: int,
        user_id: int,
        payload: release_schema.ReleaseUpdate,
) -> models.Release:
    release = (await db.execute(select(models.Release).where(
        models.Release.id == release_id))).scalars().first()
    product = await __get_product(db, release.product_id)
    releaser = get_releaser_class(product)(db)
    return await releaser.update_release(release_id, payload, user_id)


async def commit_release(
        db: Session,
        release_id: int,
        user_id: int,
) -> typing.Tuple[models.Release, str]:
    release = (await db.execute(select(models.Release).where(
        models.Release.id == release_id))).scalars().first()
    product = await __get_product(db, release.product_id)
    releaser = get_releaser_class(product)(db)
    return await releaser.commit_release(release_id, user_id)

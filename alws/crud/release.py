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
    db: Session,
    page_number: typing.Optional[int] = None,
    release_id: int = None,
    product_id: int = None,
    platform_id: int = None,
    status: int = None,
) -> typing.Union[typing.List[models.Release], models.Release]:

    def generate_query(count=False):
        query = select(models.Release).options(
            selectinload(models.Release.owner),
            selectinload(models.Release.platform),
            selectinload(models.Release.product),
        ).order_by(models.Release.id.desc())
        if count:
            query = select(func.count(models.Release.id))
        if release_id:
            query = query.where(models.Release.id == release_id)
        # TODO: Add here filter by packages and modules
        # These links could be helpful for filtering by JSON
        # https://github.com/sqlalchemy/sqlalchemy/discussions/7991
        # https://www.postgresql.org/docs/9.5/functions-json.html
        if status:
            query = query.filter(
                models.Release.status == status,
            )
        if product_id:
            query = query.filter(
                models.Release.product_id == product_id,
            )
        if platform_id:
            query = query.filter(
                models.Release.platform_id == platform_id,
            )
        if page_number and not count:
            query = query.slice(10 * page_number - 10, 10 * page_number)
        return query

    if release_id:
        return (await db.execute(generate_query())).scalars().first()
    if page_number:
        return {
            'releases': (await db.execute(generate_query())).scalars().all(),
            'total_releases': (
                await db.execute(generate_query(count=True))
            ).scalar(),
            'current_page': page_number,
        }
    return (await db.execute(generate_query())).scalars().all()


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

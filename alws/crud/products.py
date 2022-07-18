import typing

from sqlalchemy.future import select
from sqlalchemy.orm import selectinload

from alws import models
from alws.database import Session
from alws.schemas.product_schema import ProductCreate


__all__ = [
    'create_product',
    'get_products',
]


async def create_product(
        db: Session, payload: ProductCreate) -> models.Product:
    test_team_id = (await db.execute(select(models.Team.id).where(
        models.Team.id == payload.team_id))).scalars().first()
    if not test_team_id:
        raise ValueError(f'Incorrect team ID: {payload.team_id}')

    test_owner_id = (await db.execute(select(models.User.id).where(
        models.User.id == payload.owner_id))).scalars().first()
    if not test_owner_id:
        raise ValueError(f'Incorrect owner ID: {payload.owner_id}')

    product = (await db.execute(select(models.Product).where(
        models.Product.name == payload.name))).scalars().first()
    if product:
        return product

    product = models.Product(**payload.dict())
    db.add(product)
    await db.flush()
    await db.refresh(product)
    return product


async def get_products(db: Session) -> typing.List[models.Product]:
    return (await db.execute(select(models.Product).options(
        selectinload(models.Product.owner),
        selectinload(models.Product.team),
    ))).scalars().all()

import typing

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from alws import models
from alws.errors import DataNotFoundError, SignKeyAlreadyExistsError
from alws.schemas import sign_schema


async def get_sign_keys(db: AsyncSession) -> typing.List[models.SignKey]:
    result = await db.execute(select(models.SignKey))
    return result.scalars().all()


async def create_sign_key(
        db: AsyncSession, payload: sign_schema.SignKeyCreate) -> models.SignKey:
    check = await db.execute(select(models.SignKey.id).where(
        models.SignKey.keyid == payload.keyid))
    if check.scalars().first():
        raise SignKeyAlreadyExistsError(
            f'Key with keyid {payload.keyid} already exists')
    sign_key = models.SignKey(**payload.dict())
    db.add(sign_key)
    await db.commit()
    await db.refresh(sign_key)
    return sign_key


async def update_sign_key(
        db: AsyncSession, key_id: int,
        payload: sign_schema.SignKeyUpdate) -> models.SignKey:
    sign_key = await db.execute(select(models.SignKey).get(key_id))
    if not sign_key:
        raise DataNotFoundError(f'Sign key with ID {key_id} does not exist')
    for k, v in payload.dict().items():
        setattr(sign_key, k, v)
    db.add(sign_key)
    await db.commit()
    await db.refresh(sign_key)
    return sign_key

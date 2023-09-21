import typing

from sqlalchemy.future import select
from sqlalchemy.orm import Session, selectinload

from alws import models
from alws.errors import DataNotFoundError, SignKeyAlreadyExistsError
from alws.models import User
from alws.perms import actions
from alws.perms.authorization import can_perform
from alws.schemas import sign_schema


async def get_sign_keys(
        db: Session,
        user: User,
) -> typing.List[models.SignKey]:
    result = await db.execute(select(models.SignKey).options(
        selectinload(models.SignKey.owner),
        selectinload(models.SignKey.roles).selectinload(
            models.UserRole.actions
        ),
    ))
    suitable_keys = [
        sign_key for sign_key in result.scalars().all()
        if can_perform(sign_key, user, actions.UseSignKey.name)
    ]
    return suitable_keys


async def create_sign_key(
        db: Session, payload: sign_schema.SignKeyCreate) -> models.SignKey:
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
        db: Session, key_id: int,
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

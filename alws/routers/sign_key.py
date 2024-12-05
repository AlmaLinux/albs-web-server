import typing

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    status,
)
from fastapi_sqla import AsyncSessionDependency
from sqlalchemy.ext.asyncio import AsyncSession

from alws.auth import get_current_user
from alws.crud import sign_key
from alws.dependencies import get_async_db_key
from alws.errors import PlatformMissingError, SignKeyAlreadyExistsError
from alws.schemas import sign_schema

router = APIRouter(
    prefix='/sign-keys',
    tags=['sign-keys'],
    dependencies=[Depends(get_current_user)],
)


@router.get('/', response_model=typing.List[sign_schema.SignKey])
async def get_sign_keys(
    db: AsyncSession = Depends(AsyncSessionDependency(key=get_async_db_key())),
    user=Depends(get_current_user),
):
    keys = await sign_key.get_sign_keys(db, user)
    for key in keys:
        if key.platforms:
            key.platform_ids = [pl.id for pl in key.platforms]
    return keys


@router.post(
    '/new/',
    response_model=sign_schema.SignKey,
    status_code=status.HTTP_201_CREATED,
)
async def create_sign_key(
    payload: sign_schema.SignKeyCreate,
    db: AsyncSession = Depends(AsyncSessionDependency(key=get_async_db_key())),
    user=Depends(get_current_user),
):
    try:
        payload.owner_id = user.id
        key = await sign_key.create_sign_key(db, payload)
        if payload.platform_ids:
            key.platform_ids = [pl.id for pl in key.platforms]
        return key
    except (PlatformMissingError, SignKeyAlreadyExistsError) as e:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(e))


@router.put('/{sign_key_id}/', response_model=sign_schema.SignKey)
async def modify_sign_key(
    sign_key_id: int,
    payload: sign_schema.SignKeyUpdate,
    db: AsyncSession = Depends(AsyncSessionDependency(key=get_async_db_key())),
):
    return await sign_key.update_sign_key(db, sign_key_id, payload)

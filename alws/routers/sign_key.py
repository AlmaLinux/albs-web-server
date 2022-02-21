import typing

from fastapi import APIRouter, Depends

from alws.crud import sign_key
from alws.dependencies import JWTBearer, get_sync_db
from alws.schemas import sign_schema


router = APIRouter(
    prefix='/sign-keys',
    tags=['sign-keys'],
    dependencies=[Depends(JWTBearer())]
)


@router.get('/', response_model=typing.List[sign_schema.SignKey])
async def get_sign_keys():
    with get_sync_db() as db:
        return await sign_key.get_sign_keys(db)


@router.post('/new/', response_model=sign_schema.SignKey)
async def create_sign_key(payload: sign_schema.SignKeyCreate):
    with get_sync_db() as db:
        return await sign_key.create_sign_key(db, payload)


@router.put('/{sign_key_id}/', response_model=sign_schema.SignKey)
async def modify_sign_key(
        sign_key_id: int,
        payload: sign_schema.SignKeyUpdate
):
    with get_sync_db() as db:
        return await sign_key.update_sign_key(db, sign_key_id, payload)

import typing

from fastapi import APIRouter, Depends

from alws import database
from alws.auth import get_current_user
from alws.crud import sign_key
from alws.dependencies import get_db
from alws.schemas import sign_schema


router = APIRouter(
    prefix='/sign-keys',
    tags=['sign-keys'],
    dependencies=[Depends(get_current_user)]
)


@router.get('/', response_model=typing.List[sign_schema.SignKey])
async def get_sign_keys(db: database.Session = Depends(get_db)):
    return await sign_key.get_sign_keys(db)


@router.post('/new/', response_model=sign_schema.SignKey)
async def create_sign_key(payload: sign_schema.SignKeyCreate,
                          db: database.Session = Depends(get_db)):
    return await sign_key.create_sign_key(db, payload)


@router.put('/{sign_key_id}/', response_model=sign_schema.SignKey)
async def modify_sign_key(sign_key_id: int, payload: sign_schema.SignKeyUpdate,
                          db: database.Session = Depends(get_db)):
    return await sign_key.update_sign_key(db, sign_key_id, payload)

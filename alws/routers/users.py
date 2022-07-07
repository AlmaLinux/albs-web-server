import typing

from fastapi import APIRouter, Depends

from alws.dependencies import get_db
from alws import database
from alws.crud import user as user_crud
from alws.schemas import user_schema


router = APIRouter(
    prefix='/users',
    tags=['users'],
)


@router.get(
    '/all_users',
    response_model=typing.List[user_schema.User],
)
async def get_all_users(db: database.Session = Depends(get_db)):
    return await user_crud.get_all_users(db)

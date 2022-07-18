import typing

from fastapi import APIRouter, Depends

from alws import database
from alws.crud import roles
from alws.dependencies import get_db, JWTBearer
from alws.schemas import role_schema


router = APIRouter(
    prefix='/roles',
    tags=['roles'],
    dependencies=[Depends(JWTBearer())]
)


@router.get('/', response_model=typing.List[role_schema.Role])
async def get_roles(db: database.Session = Depends(get_db)):
    return await roles.get_roles(db)

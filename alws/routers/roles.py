import typing

from fastapi import APIRouter, Depends
from fastapi_sqla.asyncio_support import AsyncSession

from alws.auth import get_current_user
from alws.crud import roles
from alws.schemas import role_schema


router = APIRouter(
    prefix='/roles',
    tags=['roles'],
    dependencies=[Depends(get_current_user)]
)


@router.get('/', response_model=typing.List[role_schema.Role])
async def get_roles(db: AsyncSession = Depends()):
    return await roles.get_roles(db)

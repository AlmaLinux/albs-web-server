import typing

from fastapi import APIRouter, Depends
from fastapi_sqla import AsyncSessionDependency
from sqlalchemy.ext.asyncio import AsyncSession

from alws.auth import get_current_user
from alws.crud import roles
from alws.dependencies import get_async_db_key
from alws.schemas import role_schema

router = APIRouter(
    prefix='/roles', tags=['roles'], dependencies=[Depends(get_current_user)]
)


@router.get('/', response_model=typing.List[role_schema.Role])
async def get_roles(
    db: AsyncSession = Depends(AsyncSessionDependency(key=get_async_db_key())),
):
    return await roles.get_roles(db)

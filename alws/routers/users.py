import typing

from fastapi import APIRouter, Depends
from fastapi_sqla.asyncio_support import AsyncSession

from alws.auth import get_current_superuser
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
async def get_all_users(db: AsyncSession = Depends()):
    return await user_crud.get_all_users(db)


@router.patch('/{user_id}/activate')
async def activate_user(user_id: int, db: AsyncSession = Depends(),
                      _=Depends(get_current_superuser)
                      ) -> user_schema.UserOpResult:
    await user_crud.activate_user(user_id, db)
    return user_schema.UserOpResult(success=True)


@router.patch('/{user_id}/deactivate')
async def deactivate_user(user_id: int, db: AsyncSession = Depends(),
                          _=Depends(get_current_superuser)
                          ) -> user_schema.UserOpResult:
    await user_crud.deactivate_user(user_id, db)
    return user_schema.UserOpResult(success=True)

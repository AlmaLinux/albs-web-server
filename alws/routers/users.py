import typing

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    status,
)
from fastapi_sqla import AsyncSessionDependency
from sqlalchemy.ext.asyncio import AsyncSession

from alws.auth import get_current_superuser, get_current_user
from alws.crud import user as user_crud
from alws.dependencies import get_async_db_key
from alws.errors import PermissionDenied, UserError
from alws.models import User
from alws.schemas import role_schema, user_schema

router = APIRouter(
    prefix='/users',
    tags=['users'],
)


@router.get(
    '/all_users',
    response_model=typing.List[user_schema.User],
)
async def get_all_users(
    db: AsyncSession = Depends(AsyncSessionDependency(key=get_async_db_key())),
):
    return await user_crud.get_all_users(db)


@router.put('/{user_id}', response_model=user_schema.UserOpResult)
async def modify_user(
    user_id: int,
    payload: user_schema.UserUpdate,
    db: AsyncSession = Depends(AsyncSessionDependency(key=get_async_db_key())),
    _=Depends(get_current_superuser),
) -> user_schema.UserOpResult:
    try:
        await user_crud.update_user(db, user_id, payload)
        return user_schema.UserOpResult(success=True)
    except UserError as err:
        raise HTTPException(
            detail=str(err),
            status_code=status.HTTP_400_BAD_REQUEST,
        )


@router.delete('/{user_id}/remove')
async def remove_user(
    user_id: int,
    db: AsyncSession = Depends(AsyncSessionDependency(key=get_async_db_key())),
    _=Depends(get_current_superuser),
) -> user_schema.UserOpResult:
    try:
        await user_crud.remove_user(user_id, db)
        return user_schema.UserOpResult(
            success=True,
            message=f'User with id {user_id} has been queued for removal',
        )
    except UserError as err:
        raise HTTPException(
            detail=str(err),
            status_code=status.HTTP_400_BAD_REQUEST,
        )


@router.get('/{user_id}/roles', response_model=typing.List[role_schema.Role])
async def get_user_roles(
    user_id: int,
    db: AsyncSession = Depends(AsyncSessionDependency(key=get_async_db_key())),
    _=Depends(get_current_user),
):
    return await user_crud.get_user_roles(db, user_id)


@router.patch('/{user_id}/roles/add', response_model=user_schema.UserOpResult)
async def add_roles(
    user_id: int,
    roles_ids: typing.List[int],
    db: AsyncSession = Depends(AsyncSessionDependency(key=get_async_db_key())),
    current_user: User = Depends(get_current_user),
) -> user_schema.UserOpResult:
    try:
        await user_crud.add_roles(db, user_id, roles_ids, current_user.id)
        return user_schema.UserOpResult(
            success=True,
            message=f'Successfully added roles {roles_ids} to {user_id}',
        )
    except (PermissionDenied, Exception) as exc:
        raise HTTPException(
            detail=str(exc), status_code=status.HTTP_400_BAD_REQUEST
        )


@router.patch(
    '/{user_id}/roles/remove', response_model=user_schema.UserOpResult
)
async def remove_roles(
    user_id: int,
    roles_ids: typing.List[int],
    db: AsyncSession = Depends(AsyncSessionDependency(key=get_async_db_key())),
    current_user: User = Depends(get_current_user),
) -> user_schema.UserOpResult:
    try:
        await user_crud.remove_roles(db, user_id, roles_ids, current_user.id)
        return user_schema.UserOpResult(
            success=True,
            message=f'Successfully removed roles {roles_ids} from {user_id}',
        )
    except (PermissionDenied, Exception) as exc:
        raise HTTPException(
            detail=str(exc), status_code=status.HTTP_400_BAD_REQUEST
        )


@router.get(
    '/{user_id}/teams', response_model=typing.List[user_schema.UserTeam]
)
async def get_user_teams(
    user_id: int,
    db: AsyncSession = Depends(AsyncSessionDependency(key=get_async_db_key())),
    _=Depends(get_current_user),
):
    return await user_crud.get_user_teams(db, user_id)

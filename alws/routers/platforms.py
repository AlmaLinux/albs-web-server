import typing

from fastapi import APIRouter, Depends
from fastapi_sqla import AsyncSessionDependency
from sqlalchemy.ext.asyncio import AsyncSession

from alws.auth import get_current_user
from alws.crud import platform as pl_crud
from alws.crud import repository
from alws.dependencies import get_async_db_key
from alws.schemas import platform_schema

router = APIRouter(
    prefix='/platforms',
    tags=['platforms'],
    dependencies=[Depends(get_current_user)],
)

public_router = APIRouter(
    prefix='/platforms',
    tags=['platforms'],
)


@router.post('/', response_model=platform_schema.Platform)
async def create_platform(
    platform: platform_schema.PlatformCreate,
    db: AsyncSession = Depends(AsyncSessionDependency(key=get_async_db_key())),
):
    return await pl_crud.create_platform(db, platform)


@router.put('/', response_model=platform_schema.Platform)
async def modify_platform(
    platform: platform_schema.PlatformModify,
    db: AsyncSession = Depends(AsyncSessionDependency(key=get_async_db_key())),
):
    return await pl_crud.modify_platform(db, platform)


@public_router.get('/', response_model=typing.List[platform_schema.Platform])
async def get_platforms(
    db: AsyncSession = Depends(AsyncSessionDependency(key=get_async_db_key())),
):
    return await pl_crud.get_platforms(db)


@router.patch(
    '/{platform_id}/add-repositories', response_model=platform_schema.Platform
)
async def add_repositories_to_platform(
    platform_id: int,
    repositories_ids: typing.List[int],
    db: AsyncSession = Depends(AsyncSessionDependency(key=get_async_db_key())),
):
    return await repository.add_to_platform(db, platform_id, repositories_ids)


@router.patch(
    '/{platform_id}/remove-repositories',
    response_model=platform_schema.Platform,
)
async def remove_repositories_to_platform(
    platform_id: int,
    repositories_ids: typing.List[int],
    db: AsyncSession = Depends(AsyncSessionDependency(key=get_async_db_key())),
):
    return await repository.remove_from_platform(
        db, platform_id, repositories_ids
    )

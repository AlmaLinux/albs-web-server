import typing

from fastapi import APIRouter, Depends

from alws.crud import platform as pl_crud, repository
from alws.dependencies import JWTBearer, get_sync_db
from alws.schemas import platform_schema


router = APIRouter(
    prefix='/platforms',
    tags=['platforms'],
    dependencies=[Depends(JWTBearer())]
)


@router.post('/', response_model=platform_schema.Platform)
async def create_platform(
            platform: platform_schema.PlatformCreate,
        ):
    with get_sync_db() as db:
        return await pl_crud.create_platform(db, platform)


@router.put('/', response_model=platform_schema.Platform)
async def modify_platform(platform: platform_schema.PlatformModify):
    with get_sync_db() as db:
        return await pl_crud.modify_platform(db, platform)


@router.get('/', response_model=typing.List[platform_schema.Platform])
async def get_platforms(is_reference: bool = False):
    with get_sync_db() as db:
        return await pl_crud.get_platforms(db, is_reference)


@router.patch('/{platform_id}/add-repositories',
              response_model=platform_schema.Platform)
async def add_repositories_to_platform(
        platform_id: int,
        repositories_ids: typing.List[int]
):
    with get_sync_db() as db:
        return await repository.add_to_platform(
            db, platform_id, repositories_ids)


@router.patch('/{platform_id}/remove-repositories',
              response_model=platform_schema.Platform)
async def remove_repositories_to_platform(
        platform_id: int,
        repositories_ids: typing.List[int],
):
    with get_sync_db() as db:
        return await repository.remove_from_platform(
            db, platform_id, repositories_ids)

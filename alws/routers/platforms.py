import typing

from fastapi import APIRouter, Depends

from alws.dependencies import get_db, JWTBearer
from alws import database, crud
from alws.schemas import platform_schema


router = APIRouter(
    prefix='/platforms',
    tags=['platforms'],
    dependencies=[Depends(JWTBearer())]
)


@router.post('/', response_model=platform_schema.Platform)
async def create_platform(
            platform: platform_schema.PlatformCreate,
            db: database.Session = Depends(get_db)
        ):
    return await crud.create_platform(db, platform)


@router.put('/', response_model=platform_schema.Platform)
async def modify_platform(
            platform: platform_schema.PlatformModify,
            db: database.Session = Depends(get_db)
        ):
    return await crud.modify_platform(db, platform)


@router.get('/', response_model=typing.List[platform_schema.Platform])
async def get_platforms(db: database.Session = Depends(get_db)):
    return await crud.get_platforms(db)


@router.patch('/{platform_id}/add-repositories',
              response_model=platform_schema.Platform)
async def add_repositories_to_platform(platform_id: int,
                                       repositories_ids: typing.List[int],
                                       db: database.Session = Depends(get_db)):
    return await crud.add_to_platform(db, platform_id, repositories_ids)


@router.patch('/{platform_id}/remove-repositories',
              response_model=platform_schema.Platform)
async def remove_repositories_to_platform(platform_id: int,
                                          repositories_ids: typing.List[int],
                                          db: database.Session = Depends(get_db)):
    return await crud.remove_from_platform(db, platform_id, repositories_ids)

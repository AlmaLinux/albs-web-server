import typing

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    Request,
    status,
)
from fastapi_sqla.asyncio_support import AsyncSession

from alws import models
from alws.auth import get_current_user
from alws.crud import (
    build as build_crud,
    build_node,
    platform as platform_crud,
    platform_flavors as flavors_crud
)
from alws.errors import BuildError, DataNotFoundError
from alws.schemas import build_schema


router = APIRouter(
    prefix='/builds',
    tags=['builds'],
    dependencies=[Depends(get_current_user)]
)

public_router = APIRouter(
    prefix='/builds',
    tags=['builds'],
)


@router.post('/', response_model=build_schema.BuildCreateResponse)
async def create_build(
            build: build_schema.BuildCreate,
            user: models.User = Depends(get_current_user),
            db: AsyncSession = Depends()
        ):
    return await build_crud.create_build(db, build, user.id)


@public_router.get('/', response_model=typing.Union[
    typing.List[build_schema.Build], build_schema.BuildsResponse])
async def get_builds_per_page(
    request: Request,
    pageNumber: int,
    db: AsyncSession = Depends(),
):
    search_params = build_schema.BuildSearch(**request.query_params)
    return await build_crud.get_builds(
        db=db,
        page_number=pageNumber,
        search_params=search_params,
    )


@router.post('/get_module_preview/',
             response_model=build_schema.ModulePreview)
async def get_module_preview(
    module_request: build_schema.ModulePreviewRequest,
    db: AsyncSession = Depends()
):
    platform = await platform_crud.get_platform(
        db, module_request.platform_name
    )
    flavors = []
    if module_request.flavors:
        flavors = await flavors_crud.list_flavours(
            db, ids=module_request.flavors
        )
    return await build_crud.get_module_preview(platform, flavors, module_request)


@public_router.get('/{build_id}/', response_model=build_schema.Build)
async def get_build(build_id: int, db: AsyncSession = Depends()):
    db_build = await build_crud.get_builds(db, build_id)
    if db_build is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f'Build with {build_id=} is not found'
        )
    return db_build


@router.patch('/{build_id}/restart-failed', response_model=build_schema.Build)
async def restart_failed_build_items(build_id: int,
                                     db: AsyncSession = Depends()):
    return await build_node.update_failed_build_items(db, build_id)


@router.delete('/{build_id}/remove', status_code=status.HTTP_204_NO_CONTENT)
async def remove_build(build_id: int, db: AsyncSession = Depends()):
    try:
        await build_crud.remove_build_job(db, build_id)
    except DataNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        )
    except BuildError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        )

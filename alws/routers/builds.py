import typing

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from alws import models
from alws.auth import get_current_user
from alws.crud import build as build_crud
from alws.crud import build_node
from alws.crud import platform as platform_crud
from alws.crud import platform_flavors as flavors_crud
from alws.dependencies import get_db
from alws.errors import BuildError, DataNotFoundError
from alws.schemas import build_schema

router = APIRouter(
    prefix='/builds',
    tags=['builds'],
    dependencies=[Depends(get_current_user)],
)

public_router = APIRouter(
    prefix='/builds',
    tags=['builds'],
)


@router.post('/', response_model=build_schema.BuildCreateResponse)
async def create_build(
    build: build_schema.BuildCreate,
    user: models.User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return await build_crud.create_build(db, build, user.id)


@public_router.get(
    '/',
    response_model=typing.Union[
        typing.List[build_schema.Build],
        build_schema.BuildsResponse,
    ],
)
async def get_builds_per_page(
    pageNumber: int,
    created_by: typing.Optional[int] = None,
    project: typing.Optional[str] = None,
    ref: typing.Optional[str] = None,
    rpm_name: typing.Optional[str] = None,
    rpm_epoch: typing.Optional[str] = None,
    rpm_version: typing.Optional[str] = None,
    rpm_release: typing.Optional[str] = None,
    rpm_arch: typing.Optional[str] = None,
    platform_id: typing.Optional[int] = None,
    build_task_arch: typing.Optional[str] = None,
    released: typing.Optional[bool] = None,
    signed: typing.Optional[bool] = None,
    is_running: typing.Optional[bool] = None,
    db: AsyncSession = Depends(get_db),
):
    return await build_crud.get_builds(
        db=db,
        page_number=pageNumber,
        created_by=created_by,
        project=project,
        ref=ref,
        rpm_name=rpm_name,
        rpm_epoch=rpm_epoch,
        rpm_version=rpm_version,
        rpm_release=rpm_release,
        rpm_arch=rpm_arch,
        platform_id=platform_id,
        build_task_arch=build_task_arch,
        released=released,
        signed=signed,
        is_running=is_running,
    )


@router.post('/get_module_preview/', response_model=build_schema.ModulePreview)
async def get_module_preview(
    module_request: build_schema.ModulePreviewRequest,
    db: AsyncSession = Depends(get_db),
):
    platform = await platform_crud.get_platform(
        db,
        module_request.platform_name,
    )
    flavors = []
    if module_request.flavors:
        flavors = await flavors_crud.list_flavours(
            db,
            ids=module_request.flavors,
        )
    return await build_crud.get_module_preview(
        platform,
        flavors,
        module_request,
    )


@public_router.get('/{build_id}/', response_model=build_schema.Build)
async def get_build(build_id: int, db: AsyncSession = Depends(get_db)):
    db_build = await build_crud.get_builds(db, build_id)
    if db_build is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f'Build with {build_id=} is not found',
        )
    return db_build


@router.patch('/{build_id}/restart-failed', status_code=status.HTTP_200_OK)
async def restart_failed_build_items(
    build_id: int,
    db: AsyncSession = Depends(get_db),
):
    return await build_node.update_failed_build_items(db, build_id)


@router.patch("/{build_id}/cancel", status_code=status.HTTP_200_OK)
async def cancel_idle_build_items(
    build_id: int,
    session: AsyncSession = Depends(get_db),
):
    await build_node.mark_build_tasks_as_cancelled(session, build_id)


@router.patch(
    '/{build_id}/parallel-restart-failed',
    status_code=status.HTTP_200_OK,
)
async def parallel_restart_failed_build_items(
    build_id: int,
    db: AsyncSession = Depends(get_db),
):
    return await build_node.update_failed_build_items_in_parallel(db, build_id)


@router.delete('/{build_id}/remove', status_code=status.HTTP_204_NO_CONTENT)
async def remove_build(build_id: int, db: AsyncSession = Depends(get_db)):
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

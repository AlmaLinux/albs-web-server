import typing

from fastapi import APIRouter, Depends
from fastapi_sqla import AsyncSessionDependency
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from alws import models
from alws.auth import get_current_user
from alws.constants import ReleaseStatus
from alws.crud import release as r_crud
from alws.dependencies import get_async_db_key
from alws.dramatiq import execute_release_plan, revert_release
from alws.schemas import release_schema

router = APIRouter(
    prefix="/releases",
    tags=["releases"],
    dependencies=[Depends(get_current_user)],
)

public_router = APIRouter(
    prefix="/releases",
    tags=["releases"],
)


# TODO: add pulp db loader
@public_router.get(
    "/",
    response_model=typing.Union[
        typing.List[release_schema.Release], release_schema.ReleaseResponse
    ],
)
async def get_releases(
    pageNumber: typing.Optional[int] = None,
    product_id: typing.Optional[int] = None,
    platform_id: typing.Optional[int] = None,
    status: typing.Optional[int] = None,
    package_name: typing.Optional[str] = None,
    db: AsyncSession = Depends(AsyncSessionDependency(key=get_async_db_key())),
):
    return await r_crud.get_releases(
        db,
        page_number=pageNumber,
        product_id=product_id,
        platform_id=platform_id,
        status=status,
        package_name=package_name,
    )


@public_router.get("/{release_id}/", response_model=release_schema.Release)
async def get_release(
    release_id: int,
    db: AsyncSession = Depends(AsyncSessionDependency(key=get_async_db_key())),
):
    return await r_crud.get_releases(db, release_id=release_id)


@router.post("/new/", response_model=release_schema.Release)
async def create_new_release(
    payload: release_schema.ReleaseCreate,
    db: AsyncSession = Depends(AsyncSessionDependency(key=get_async_db_key())),
    user: models.User = Depends(get_current_user),
):
    await r_crud.check_compatible_platforms(
        db,
        payload.builds,
        payload.platform_id,
    )
    release = await r_crud.create_release(db, user.id, payload)
    return release


@router.put("/{release_id}/", response_model=release_schema.Release)
async def update_release(
    release_id: int,
    payload: release_schema.ReleaseUpdate,
    db: AsyncSession = Depends(AsyncSessionDependency(key=get_async_db_key())),
    user: models.User = Depends(get_current_user),
):
    release = await r_crud.update_release(db, release_id, user.id, payload)
    return release


@router.post(
    "/{release_id}/commit/",
    response_model=release_schema.ReleaseCommitResult,
)
async def commit_release(
    release_id: int,
    db: AsyncSession = Depends(AsyncSessionDependency(key=get_async_db_key())),
    user: models.User = Depends(get_current_user),
):
    # it's ugly hack for updating release status before execution in background
    await db.execute(
        update(models.Release)
        .where(
            models.Release.id == release_id,
        )
        .values(status=ReleaseStatus.IN_PROGRESS)
    )
    await db.flush()
    execute_release_plan.send(release_id, user.id)
    return {"message": "Release plan execution has been started"}


@router.post(
    "/{release_id}/revert/",
    response_model=release_schema.ReleaseCommitResult,
)
async def revert_db_release(
    release_id: int,
    db: AsyncSession = Depends(AsyncSessionDependency(key=get_async_db_key())),
    user: models.User = Depends(get_current_user),
):
    # it's ugly hack for updating release status before execution in background
    await db.execute(
        update(models.Release)
        .where(
            models.Release.id == release_id,
        )
        .values(status=ReleaseStatus.IN_PROGRESS)
    )
    await db.flush()
    revert_release.send(release_id, user.id)
    return {"message": "Release plan revert has been started"}


@router.delete(
    '/{release_id}/delete',
    response_model=release_schema.ReleaseCommitResult,
)
async def delete_release(
    release_id: int,
    db: AsyncSession = Depends(AsyncSessionDependency(key=get_async_db_key())),
    user: models.User = Depends(get_current_user),
):
    """
    Delete only a scheduled release
    """
    await r_crud.remove_release(
        db=db,
        release_id=release_id,
        user=user,
    )

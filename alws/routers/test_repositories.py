import typing

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi_sqla import AsyncSessionDependency
from sqlalchemy.ext.asyncio import AsyncSession
# from alws.dependencies import get_db
from alws.auth import get_current_user
from alws.crud import test_repository
from alws.dependencies import get_async_db_key
from alws.errors import DataNotFoundError, TestRepositoryError
from alws.schemas import test_repository_schema
from alws import models


router = APIRouter(
    prefix='/test_repositories',
    tags=['test_repositories'],
    dependencies=[Depends(get_current_user)],
)


@router.get(
    '/',
    response_model=typing.Union[
        typing.List[test_repository_schema.TestRepository],
        test_repository_schema.TestRepositoryResponse,
    ],
)
async def get_repositories(
    pageNumber: typing.Optional[int] = None,
    name: typing.Optional[str] = None,
    session: AsyncSession = Depends(
        AsyncSessionDependency(key=get_async_db_key())
    ),
):
    return await test_repository.get_repositories(
        session,
        page_number=pageNumber,
        name=name,
    )


@router.get(
    '/{repository_id}/',
    response_model=typing.Optional[test_repository_schema.TestRepository],
)
async def get_repository(
    repository_id: int,
    session: AsyncSession = Depends(
        AsyncSessionDependency(key=get_async_db_key())
    ),
):
    return await test_repository.get_repositories(
        session,
        repository_id=repository_id,
    )


@router.post('/create/', response_model=test_repository_schema.TestRepository)
async def create_repository(
    payload: test_repository_schema.TestRepositoryCreate,
    session: AsyncSession = Depends(
        AsyncSessionDependency(key=get_async_db_key())
    ),
):
    try:
        db_repo = await test_repository.create_repository(session, payload)
    except TestRepositoryError as exc:
        raise HTTPException(
            detail=str(exc),
            status_code=status.HTTP_400_BAD_REQUEST,
        )
    created_repo = await test_repository.get_repositories(
        session,
        repository_id=db_repo.id,
    )
    return created_repo


# @router.patch(
#     '/{repository_id}/',
#     status_code=status.HTTP_204_NO_CONTENT,
# )
async def update_test_repository(
    repository_id: int,
    payload: test_repository_schema.TestRepositoryUpdate,
    session: AsyncSessionDependency = Depends(get_async_db_key()),
    user: models.User = Depends(get_current_user),
):
    try:
        await test_repository.update_repository(
            session,
            repository_id,
            payload,
            user,
        )
    except DataNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        )


# @router.delete(
#     '/{repository_id}/remove/',
#     status_code=status.HTTP_204_NO_CONTENT,
# )
async def remove_test_repository(
    repository_id: int,
    session: AsyncSessionDependency = Depends(get_async_db_key()),
    user: models.User = Depends(get_current_user),
):
    try:
        await test_repository.delete_repository(session, repository_id, user)
    except DataNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        )


@router.post(
    '/{repository_id}/packages/create/',
    status_code=status.HTTP_201_CREATED,
)
async def create_package_mapping(
    repository_id: int,
    payload: test_repository_schema.PackageTestRepositoryCreate,
    session: AsyncSession = Depends(
        AsyncSessionDependency(key=get_async_db_key())
    ),
):
    try:
        await test_repository.create_package_mapping(
            session,
            payload,
            repository_id,
        )
    except TestRepositoryError as exc:
        raise HTTPException(
            detail=str(exc),
            status_code=status.HTTP_400_BAD_REQUEST,
        )


@router.post(
    '/{repository_id}/packages/bulk_create/',
    status_code=status.HTTP_201_CREATED,
)
async def bulk_create_package_mapping(
    repository_id: int,
    payload: typing.List[test_repository_schema.PackageTestRepositoryCreate],
    session: AsyncSession = Depends(
        AsyncSessionDependency(key=get_async_db_key())
    ),
):
    try:
        await test_repository.bulk_create_package_mapping(
            session=session,
            payload=payload,
            repository_id=repository_id,
        )
    except TestRepositoryError as exc:
        raise HTTPException(
            detail=str(exc),
            status_code=status.HTTP_400_BAD_REQUEST,
        )


@router.delete(
    '/packages/{package_id}/remove/',
    status_code=status.HTTP_204_NO_CONTENT,
)
async def remove_package_mapping(
    package_id: int,
    session: AsyncSession = Depends(
        AsyncSessionDependency(key=get_async_db_key())
    ),
):
    try:
        await test_repository.delete_package_mapping(session, package_id)
    except DataNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        )


@router.post(
    '/{repository_id}/packages/bulk_remove/',
    status_code=status.HTTP_204_NO_CONTENT,
)
async def bulk_delete_package_mapping(
    repository_id: int,
    package_ids: typing.List[int],
    session: AsyncSession = Depends(
        AsyncSessionDependency(key=get_async_db_key())
    ),
):
    await test_repository.bulk_delete_package_mapping(
        session=session,
        package_ids=package_ids,
        repository_id=repository_id,
    )

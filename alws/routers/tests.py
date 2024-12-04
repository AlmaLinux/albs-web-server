from typing import List

from fastapi import APIRouter, Depends
from fastapi_sqla import AsyncSessionDependency
from sqlalchemy.ext.asyncio import AsyncSession

from alws import dramatiq
from alws.auth import get_current_user
from alws.crud import test
from alws.dependencies import get_async_db_key
from alws.schemas import test_schema

router = APIRouter(
    prefix='/tests',
    tags=['tests'],
    dependencies=[Depends(get_current_user)],
)

public_router = APIRouter(
    prefix='/tests',
    tags=['tests'],
)


@router.post('/{test_task_id}/result/')
async def update_test_task_result(
    test_task_id: int,
    result: test_schema.TestTaskResult,
):
    dramatiq.tasks.tests.complete_test_task.send(test_task_id, result.model_dump())
    return {'ok': True}


@router.get(
    '/get_test_tasks/',
    response_model=List[test_schema.TestTaskPayload],
)
async def get_test_tasks(
    session: AsyncSession = Depends(
        AsyncSessionDependency(key=get_async_db_key())
    ),
):
    return await test.get_available_test_tasks(session)


@router.put('/build/{build_id}/restart')
async def restart_build_tests(
    build_id: int,
    db: AsyncSession = Depends(AsyncSessionDependency(key=get_async_db_key())),
):
    await test.restart_build_tests(db, build_id)
    return {'ok': True}


@router.put('/build_task/{build_task_id}/restart')
async def restart_build_task_tests(
    build_task_id: int,
    db: AsyncSession = Depends(AsyncSessionDependency(key=get_async_db_key())),
):
    await test.restart_build_task_tests(db, build_task_id)
    return {'ok': True}


@router.put('/build/{build_id}/cancel')
async def cancel_build_tests(
    build_id: int,
    db: AsyncSession = Depends(AsyncSessionDependency(key=get_async_db_key())),
):
    await test.cancel_build_tests(db, build_id)
    return {'ok': True}


@public_router.get(
    '/{build_task_id}/latest',
    response_model=List[test_schema.TestTask],
)
async def get_latest_test_results(
    build_task_id: int,
    db: AsyncSession = Depends(AsyncSessionDependency(key=get_async_db_key())),
):
    return await test.get_test_tasks_by_build_task(db, build_task_id)


@public_router.get(
    '/{build_task_id}/logs',
    response_model=List[test_schema.TestLog],
)
async def get_test_logs(
    build_task_id: int,
    db: AsyncSession = Depends(AsyncSessionDependency(key=get_async_db_key())),
):
    return await test.get_test_logs(build_task_id, db)


@public_router.get(
    '/{build_task_id}/{revision}',
    response_model=List[test_schema.TestTask],
)
async def get_latest_test_results_by_revision(
    build_task_id: int,
    revision: int,
    db: AsyncSession = Depends(AsyncSessionDependency(key=get_async_db_key())),
):
    return await test.get_test_tasks_by_build_task(
        db,
        build_task_id,
        latest=False,
        revision=revision,
    )

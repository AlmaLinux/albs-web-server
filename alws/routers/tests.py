import typing

from fastapi import APIRouter, BackgroundTasks, Depends

from alws.crud import test
from alws.dependencies import JWTBearer, get_sync_db
from alws.schemas import test_schema


router = APIRouter(
    prefix='/tests',
    tags=['tests'],
    dependencies=[Depends(JWTBearer())]
)


@router.post('/{test_task_id}/result/')
async def update_test_task_result(test_task_id: int,
                                  result: test_schema.TestTaskResult,
                                  background_tasks: BackgroundTasks,
):
    with get_sync_db() as db:
        background_tasks.add_task(
            test.complete_test_task, db, test_task_id, result)
        return {'ok': True}


@router.put('/build/{build_id}/restart')
async def restart_build_tests(build_id: int):
    with get_sync_db() as db:
        await test.restart_build_tests(db, build_id)
        return {'ok': True}


@router.put('/build_task/{build_task_id}/restart')
async def restart_build_task_tests(build_task_id: int):
    with get_sync_db() as db:
        await test.create_test_tasks(db, build_task_id)
        return {'ok': True}


@router.get('/{build_task_id}/latest',
            response_model=typing.List[test_schema.TestTask])
async def get_latest_test_results(build_task_id: int):
    with get_sync_db() as db:
        return await test.get_test_tasks_by_build_task(db, build_task_id)


@router.get('/{build_task_id}/logs',
            response_model=typing.List[test_schema.TestLog])
async def get_test_logs(build_task_id: int):
    with get_sync_db() as db:
        return await test.get_test_logs(build_task_id, db)


@router.get('/{build_task_id}/{revision}',
            response_model=typing.List[test_schema.TestTask])
async def get_latest_test_results(build_task_id: int, revision: int):
    with get_sync_db() as db:
        return await test.get_test_tasks_by_build_task(
            db, build_task_id, latest=False, revision=revision)

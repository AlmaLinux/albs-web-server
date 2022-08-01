import typing

from fastapi import APIRouter, Depends

from alws import database, dramatiq
from alws.auth import get_current_user
from alws.crud import test
from alws.dependencies import get_db
from alws.schemas import test_schema


router = APIRouter(
    prefix='/tests',
    tags=['tests'],
    dependencies=[Depends(get_current_user)]
)

public_router = APIRouter(
    prefix='/tests',
    tags=['tests'],
)


@router.post('/{test_task_id}/result/')
async def update_test_task_result(test_task_id: int,
                                  result: test_schema.TestTaskResult):
    dramatiq.tests.complete_test_task.send(test_task_id, result.dict())
    return {'ok': True}


@router.put('/build/{build_id}/restart')
async def restart_build_tests(build_id: int,
                              db: database.Session = Depends(get_db)):
    await test.restart_build_tests(db, build_id)
    return {'ok': True}


@router.put('/build_task/{build_task_id}/restart')
async def restart_build_task_tests(build_task_id: int,
                                   db: database.Session = Depends(get_db)):
    await test.create_test_tasks(db, build_task_id)
    return {'ok': True}


@public_router.get('/{build_task_id}/latest',
                   response_model=typing.List[test_schema.TestTask])
async def get_latest_test_results(build_task_id: int,
                                  db: database.Session = Depends(get_db)):
    return await test.get_test_tasks_by_build_task(db, build_task_id)


@public_router.get('/{build_task_id}/logs',
                   response_model=typing.List[test_schema.TestLog])
async def get_test_logs(build_task_id: int,
                        db: database.Session = Depends(get_db)):
    return await test.get_test_logs(build_task_id, db)


@public_router.get('/{build_task_id}/{revision}',
                   response_model=typing.List[test_schema.TestTask])
async def get_latest_test_results(build_task_id: int, revision: int,
                                  db: database.Session = Depends(get_db)):
    return await test.get_test_tasks_by_build_task(
        db, build_task_id, latest=False, revision=revision)

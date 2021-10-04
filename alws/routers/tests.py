import typing

from fastapi import APIRouter, Depends

from alws import crud, database
from alws.dependencies import get_db, JWTBearer
from alws.schemas import test_schema


router = APIRouter(
    prefix='/tests',
    tags=['tests'],
    dependencies=[Depends(JWTBearer())]
)


@router.post('/{test_task_id}/result/')
async def update_test_task_result(test_task_id: int,
                                  result: test_schema.TestTaskResult,
                                  db: database.Session = Depends(get_db)):
    await crud.complete_test_task(db, test_task_id, result)
    return {'ok': True}


@router.put('/build/{build_id}/restart')
async def restart_build_tests(build_id: int,
                              db: database.Session = Depends(get_db)):
    await crud.restart_build_tests(db, build_id)
    return {'ok': True}


@router.put('/build_task/{build_task_id}/restart')
async def restart_build_task_tests(build_task_id: int,
                                   db: database.Session = Depends(get_db)):
    await crud.create_test_tasks(db, build_task_id)
    return {'ok': True}


@router.get('/{build_task_id}/latest',
            response_model=typing.List[test_schema.TestTask])
async def get_latest_test_results(build_task_id: int,
                                  db: database.Session = Depends(get_db)):
    return await crud.get_test_tasks_by_build_task(db, build_task_id)


@router.get('/{build_task_id}/{revision}',
            response_model=typing.List[test_schema.TestTask])
async def get_latest_test_results(build_task_id: int, revision: int,
                                  db: database.Session = Depends(get_db)):
    return await crud.get_test_tasks_by_build_task(
        db, build_task_id, latest=False, revision=revision)

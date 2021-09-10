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

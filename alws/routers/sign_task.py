import typing

from fastapi import APIRouter, Depends, Query

from alws import database
from alws.crud import sign_task
from alws.dependencies import get_db, JWTBearer
from alws.schemas import sign_schema


router = APIRouter(
    prefix='/sign-tasks',
    tags=['sign-tasks'],
    dependencies=[Depends(JWTBearer())]
)


@router.get('/', response_model=typing.List[sign_schema.SignTask])
async def get_sign_tasks(build_id: int = None,
                         db: database.Session = Depends(get_db)):
    return await sign_task.get_sign_tasks(db, build_id=build_id)


@router.post('/', response_model=sign_schema.SignTask)
async def create_sign_task(payload: sign_schema.SignTaskCreate,
                           db: database.Session = Depends(get_db)):
    return await sign_task.create_sign_task(db, payload)


@router.post('/get_sign_task/',
             response_model=typing.Union[dict, sign_schema.AvailableSignTask])
async def get_available_sign_task(
        payload: sign_schema.SignTaskGet,
        db: database.Session = Depends(get_db)):
    result = await sign_task.get_available_sign_task(db, payload.key_ids)
    if any([not result.get(item) for item in
            ['build_id', 'id', 'keyid', 'packages']]):
        return {}
    return result


@router.post('/{sign_task_id}/complete/',
             response_model=sign_schema.SignTaskCompleteResponse)
async def complete_sign_task(
        sign_task_id: int, payload: sign_schema.SignTaskComplete,
        db: database.Session = Depends(get_db)):
    await sign_task.complete_sign_task(db, sign_task_id, payload)
    return {'success': True}

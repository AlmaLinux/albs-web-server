from fastapi import APIRouter, Depends

from alws import crud, database
from alws.dependencies import get_db, JWTBearer
from alws.schemas import sign_node_schema


router = APIRouter(
    prefix='/sign_node',
    tags=['builds'],
    dependencies=[Depends(JWTBearer())]
)


@router.post(
    '/{task_id}/sign_start',
    response_model=sign_node_schema.SignStartDone
)
async def sign_start(
            task_id: int,
            sign_start: sign_node_schema.RequestSignStart,
            db: database.Session = Depends(get_db)
        ):
    task = await crud.sign_start(db, task_id, sign_start)
    if not task:
        return
    response = {
        'task_id': task.id
    }
    return response


@router.post('/sign_done')
async def sign_done(
            sign_done: sign_node_schema.SignDone,
            db: database.Session = Depends(get_db)
        ):
    return await crud.sign_done(db, sign_done)


@router.get('/get_task', response_model=sign_node_schema.Task)
async def get_sign_task(
            request: sign_node_schema.RequestSignTask,
            db: database.Session = Depends(get_db)
        ):
    task = await crud.get_available_sign_task(db, request)
    if not task:
        return
    response = {
        'id': task.id,
        'arch': task.arch,
        'ref': task.ref,
        'platform': task.platform,
        'packages': [],
        'repositories': [],
        'pgp_keyid': task.build.pgp_key_id,
        'created_by': {
            'name': task.build.user.username,
            'email': task.build.user.email
        }
    }
    for artifact in task.artifacts:
        response['packages'].append({
            'package_type': artifact.type,
            'download_url': artifact.href,
            'file_name': artifact.name,
        })
    return response

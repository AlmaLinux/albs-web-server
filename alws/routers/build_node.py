import itertools

from fastapi import APIRouter, Depends

from alws import crud, database
from alws.dependencies import get_db, JWTBearer
from alws.schemas import build_node_schema


router = APIRouter(
    prefix='/build_node',
    tags=['builds'],
    dependencies=[Depends(JWTBearer())]
)


@router.post('/ping')
async def ping(
            node_status: build_node_schema.Ping,
            db: database.Session = Depends(get_db)
        ):
    if not node_status.active_tasks:
        return
    await crud.ping_tasks(db, node_status.active_tasks)


@router.post('/build_done')
async def build_done(
            build_done: build_node_schema.BuildDone,
            db: database.Session = Depends(get_db)
        ):
    return await crud.build_done(db, build_done)


@router.get('/get_task', response_model=build_node_schema.Task)
async def get_task(
            db: database.Session = Depends(get_db)
        ):
    task = await crud.get_available_build_task(db)
    if not task:
        return
    response = {
        'id': task.id,
        'arch': task.arch,
        'ref': task.ref,
        'platform': task.platform,
        'repositories': [],
        'created_by': {
            'name': task.build.user.username,
            'email': task.build.user.email
        }
    }
    for repo in itertools.chain(task.platform.repos, task.build.repos):
        if repo.arch == task.arch and repo.type != 'build_log':
            response['repositories'].append(repo)
    for build in task.build.linked_builds:
        for repo in build.repos:
            if repo.arch == task.arch and repo.type != 'build_log':
                response['repositories'].append(repo)
    return response

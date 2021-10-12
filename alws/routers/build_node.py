import itertools

from fastapi import APIRouter, Depends

from alws import crud, database
from alws.dependencies import get_db, JWTBearer
from alws.schemas import build_task_schema


router = APIRouter(
    prefix='/build_node',
    tags=['builds'],
    dependencies=[Depends(JWTBearer())]
)


@router.post('/ping')
async def ping(
            node_status: build_task_schema.Ping,
            db: database.Session = Depends(get_db)
        ):
    if not node_status.active_tasks:
        return
    await crud.ping_tasks(db, node_status.active_tasks)


@router.post('/build_done')
async def build_done(
            build_done: build_task_schema.BuildDone,
            db: database.Session = Depends(get_db)
        ):
    await crud.build_done(db, build_done)
    # need add some logic after discussing with team
    # await crud.add_distributions_after_rebuild(db, build_done)
    await crud.create_test_tasks(db, build_done.task_id)
    return {'ok': True}


@router.get('/get_task', response_model=build_task_schema.Task)
async def get_task(
            request: build_task_schema.RequestTask,
            db: database.Session = Depends(get_db)
        ):
    task = await crud.get_available_build_task(db, request)
    if not task:
        return
    response = {
        'id': task.id,
        'arch': task.arch,
        'ref': task.ref,
        'platform': build_task_schema.TaskPlatform.from_orm(task.platform),
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
    if task.build.mock_options:
        platform_data = response['platform'].data
        for k, v in task.build.mock_options.items():
            if k in ('module_enable', 'target_arch'):
                platform_data['mock'][k] = v
            elif k == 'yum_exclude':
                platform_data['yum']['exclude'] = ' '.join(v)
            elif k in ('with', 'without'):
                for i in v:
                    platform_data['definitions'][f'_{k}_{i}'] = f'--{k}-{i}'
            else:
                for v_k, v_v in v.items():
                    platform_data['definitions'][v_k] = v_v
    return response

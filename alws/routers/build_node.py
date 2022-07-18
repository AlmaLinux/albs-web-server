import datetime
import itertools

from fastapi import APIRouter, Depends, Response, status
from dramatiq import pipeline

from alws import database
from alws import dramatiq
from alws.config import settings
from alws.crud import build_node
from alws.dependencies import get_db, JWTBearer
from alws.schemas import build_node_schema
from alws.constants import BuildTaskStatus


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
        return {}
    await build_node.ping_tasks(db, node_status.active_tasks)
    return {}


@router.post('/build_done')
async def build_done(
            build_done_: build_node_schema.BuildDone,
            response: Response,
            db: database.Session = Depends(get_db),
        ):
    build_task = await build_node.get_build_task(db, build_done_.task_id)
    if BuildTaskStatus.is_finished(build_task.status):
        response.status_code = status.HTTP_409_CONFLICT
        return {'ok': False}
    # We're setting build task timestamp to 3 hours upwards, so
    # dramatiq can have a time to complete task and build node
    # won't rebuild task again and again while it's in the queue
    # in the future this probably should be handled somehow better 
    build_task.ts = datetime.datetime.now() + datetime.timedelta(hours=3)
    await db.commit()
    if not await build_node.log_repo_exists(db, build_task):
        pipe = pipeline([
            dramatiq.create_log_repo.message(build_task.id),
            dramatiq.build_done.message_with_options(args=(build_done_.dict(), ), pipe_ignore=True)
        ])
        pipe.run()
    else:
        dramatiq.build_done.send(build_done_.dict())
    return {'ok': True}


@router.get('/get_task', response_model=build_node_schema.Task)
async def get_task(
            request: build_node_schema.RequestTask,
            db: database.Session = Depends(get_db)
        ):
    task = await build_node.get_available_build_task(db, request)
    if not task:
        return
    # generate full url to builted SRPM for using less memory in database
    built_srpm_url = task.built_srpm_url
    srpm_hash = None
    if built_srpm_url is not None:
        built_srpm_url = "{}/pulp/content/builds/{}".format(
            settings.pulp_host, task.built_srpm_url)
        srpm_hash = next(
            artifact.cas_hash
            for artifact in task.artifacts
            if artifact.name.endswith('.src.rpm')
        )
    response = {
        'id': task.id,
        'arch': task.arch,
        'build_id': task.build_id,
        'ref': task.ref,
        'platform': build_node_schema.TaskPlatform.from_orm(task.platform),
        'repositories': [],
        'built_srpm_url': built_srpm_url,
        'is_secure_boot': task.is_secure_boot,
        'alma_commit_cas_hash': task.alma_commit_cas_hash,
        'srpm_hash': srpm_hash,
        'created_by': {
            'name': task.build.owner.username,
            'email': task.build.owner.email
        }
    }
    for repo in itertools.chain(task.platform.repos, task.build.repos):
        if repo.arch == task.arch and repo.type != 'build_log':
            response['repositories'].append(repo)
    for build in task.build.linked_builds:
        for repo in build.repos:
            if repo.arch == task.arch and repo.type != 'build_log':
                response['repositories'].append(repo)
    if task.build.platform_flavors:
        for flavour in task.build.platform_flavors:
            for repo in flavour.repos:
                if repo.arch == task.arch:
                    response['repositories'].append(repo)
    if task.build.mock_options:
        response['platform'].add_mock_options(task.build.mock_options)
    if task.mock_options:
        response['platform'].add_mock_options(task.mock_options)
    if task.rpm_module:
        module = task.rpm_module
        module_build_options = {'definitions': {
            '_module_build': '1',
            'modularitylabel': ':'.join([
                module.name,
                module.stream,
                module.version,
                module.context
            ])
        }}
        response['platform'].add_mock_options(module_build_options)
    return response

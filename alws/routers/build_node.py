import datetime
import itertools
import typing

from fastapi import APIRouter, Depends, Response, status
from fastapi_sqla import AsyncSessionDependency
from sqlalchemy.ext.asyncio import AsyncSession

from alws import dramatiq
from alws.auth import get_current_user
from alws.config import settings
from alws.constants import BuildTaskRefType, BuildTaskStatus
from alws.crud import build_node
from alws.dependencies import get_async_db_key
from alws.schemas import build_node_schema

router = APIRouter(
    prefix="/build_node",
    tags=["builds"],
    dependencies=[Depends(get_current_user)],
)


@router.post("/ping")
async def ping(
    node_status: build_node_schema.Ping,
    db: AsyncSession = Depends(AsyncSessionDependency(key=get_async_db_key())),
):
    if not node_status.active_tasks:
        return {}
    await build_node.ping_tasks(db, node_status.active_tasks)
    return {}


@router.post("/build_done")
async def build_done(
    build_done_: build_node_schema.BuildDone,
    response: Response,
    db: AsyncSession = Depends(AsyncSessionDependency(key=get_async_db_key())),
):
    build_task = await build_node.get_build_task(db, build_done_.task_id)
    if BuildTaskStatus.is_finished(build_task.status):
        response.status_code = status.HTTP_409_CONFLICT
        return {"ok": False}
    # We're setting build task timestamp to 3 hours upwards, so
    # dramatiq can have a time to complete task and build node
    # won't rebuild task again and again while it's in the queue
    # in the future this probably should be handled somehow better
    build_task.ts = datetime.datetime.utcnow() + datetime.timedelta(hours=3)
    await db.flush()
    actor = dramatiq.build_done
    if build_task.arch == 'src':
        actor = dramatiq.sources_build_done
    actor.send(build_done_.model_dump())
    return {"ok": True}


@router.post(
    "/get_task",
    response_model=typing.Optional[build_node_schema.Task],
)
async def get_task(
    request: build_node_schema.RequestTask,
    db: AsyncSession = Depends(AsyncSessionDependency(key=get_async_db_key())),
):
    task = await build_node.get_available_build_task(db, request)
    if not task:
        return
    # generate full url to builted SRPM for using less memory in database
    built_srpm_url = task.built_srpm_url
    srpm_hash = None
    if built_srpm_url is not None:
        built_srpm_url = "{}/pulp/content/builds/{}".format(
            settings.pulp_host, task.built_srpm_url
        )
        srpm_hash = next(
            (
                artifact.cas_hash
                for artifact in task.artifacts
                if artifact.name.endswith(".src.rpm")
            ),
            None,
        )
    response = {
        "id": task.id,
        "arch": task.arch,
        "build_id": task.build_id,
        "ref": task.ref,
        "platform": build_node_schema.TaskPlatform.from_orm(task.platform),
        "repositories": [],
        "built_srpm_url": built_srpm_url,
        "is_secure_boot": task.is_secure_boot,
        "alma_commit_cas_hash": task.alma_commit_cas_hash,
        "srpm_hash": srpm_hash,
        "created_by": {
            "name": task.build.owner.username,
            "email": task.build.owner.email,
        },
    }
    supported_arches = request.supported_arches
    if 'src' in request.supported_arches:
        supported_arches.remove('src')
    task_arch = task.arch
    if task_arch == 'src':
        task_arch = supported_arches[0]
    for repo in itertools.chain(task.platform.repos, task.build.repos):
        if repo.arch == task_arch and repo.type != "build_log":
            response["repositories"].append(repo)
    for build in task.build.linked_builds:
        for repo in build.repos:
            if repo.arch == task_arch and repo.type != "build_log":
                response["repositories"].append(repo)
    if task.build.platform_flavors:
        for flavour in task.build.platform_flavors:
            if flavour.data:
                for key in ("macros", "secure_boot_macros"):
                    if (
                        "mock" not in flavour.data
                        or key not in flavour.data["mock"]
                    ):
                        continue
                    if key not in response["platform"].data["mock"]:
                        response["platform"].data["mock"][key] = {}
                    response["platform"].data["mock"][key].update(
                        flavour.data["mock"][key]
                    )
                if "chroot_setup_cmd" in flavour.data.get('mock', {}):
                    response["platform"].data["mock"]["chroot_setup_cmd"] = (
                        flavour.data["mock"]["chroot_setup_cmd"]
                    )
                if "use_host_resolv" in flavour.data.get('mock', {}):
                    response["platform"].data["mock"]["use_host_resolv"] = (
                        flavour.data["mock"]["use_host_resolv"]
                    )
                if "dnf_common_opts" in flavour.data.get('mock', {}):
                    if "dnf_common_opts" not in response["platform"].data["mock"]:
                        response["platform"].data["mock"]["dnf_common_opts"] = []
                    response["platform"].data["mock"]["dnf_common_opts"].extend(
                        flavour.data["mock"]["dnf_common_opts"]
                    )
                if "definitions" in flavour.data:
                    response["platform"].data["definitions"].update(
                        flavour.data["definitions"]
                    )
            for repo in flavour.repos:
                if repo.arch == task_arch:
                    response["repositories"].append(repo)

    # TODO: Get rid of this fixes when all affected builds would be processed
    # mock_enabled flag can be None for old build/flavour/platform repos
    for repo in response["repositories"]:
        if repo.mock_enabled is None:
            repo.mock_enabled = True
    # ref_type can be None for old modular builds
    if task.ref.ref_type is None:
        task.ref.ref_type = BuildTaskRefType.GIT_BRANCH

    if task.build.mock_options:
        response["platform"].add_mock_options(task.build.mock_options)
    if task.mock_options:
        response["platform"].add_mock_options(task.mock_options)
    if task.rpm_modules:
        module = next((m for m in task.rpm_modules if '-devel' not in m.name))
        module_build_options = {
            "definitions": {
                "_module_build": "1",
                "modularitylabel": ":".join([
                    module.name,
                    module.stream,
                    module.version,
                    module.context,
                ]),
            }
        }
        response["platform"].add_mock_options(module_build_options)
    return response

import hashlib
from typing import AsyncIterable

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from alws.crud.build import get_builds
from alws.crud.build_node import safe_build_done
from alws.dramatiq.build import _start_build
from alws.models import Build
from alws.schemas.build_node_schema import BuildDone
from alws.schemas.build_schema import BuildCreate
from tests.test_utils.pulp_utils import get_artifact_href


@pytest.fixture(autouse=True)
def patch_dramatiq_actor_send(monkeypatch):
    def func(*args, **kwargs):
        return

    monkeypatch.setattr("dramatiq.Actor.send", func)


@pytest.mark.anyio
@pytest.fixture
async def start_modular_build(
    modular_build: Build,
    modular_build_payload: dict,
    create_module,
    create_build_rpm_repo,
    create_log_repo,
    modify_repository,
):
    await _start_build(modular_build.id, BuildCreate(**modular_build_payload))


@pytest.mark.anyio
@pytest.fixture
async def start_build(
    regular_build: Build,
    build_payload: dict,
    create_build_rpm_repo,
    create_log_repo,
    modify_repository,
):
    await _start_build(regular_build.id, BuildCreate(**build_payload))


@pytest.mark.anyio
@pytest.fixture
async def build_done(
    session: AsyncSession,
    regular_build: Build,
    start_build,
    create_entity,
    get_rpm_packages_info,
):
    build = await get_builds(db=session, build_id=regular_build.id)
    await session.close()
    for build_task in build.tasks:
        payload = {
            "task_id": build_task.id,
            "status": "done",
            "stats": {},
            "artifacts": [
                {
                    "name": name,
                    "type": "rpm",
                    "href": get_artifact_href(),
                    "sha256": hashlib.sha256().hexdigest(),
                }
                for name in (
                    "chan-0.0.4-3.el8.src.rpm",
                    f"chan-0.0.4-3.el8.{build_task.arch}.rpm",
                )
            ],
        }
        await safe_build_done(session, BuildDone(**payload))


@pytest.mark.anyio
@pytest.fixture
async def modular_build_done(
    session: AsyncSession,
    modular_build: Build,
    start_modular_build,
    create_entity,
    get_rpm_packages_info,
    get_repo_modules_yaml,
    get_repo_modules,
):
    build = await get_builds(db=session, build_id=modular_build.id)
    await session.close()
    for build_task in build.tasks:
        payload = {
            "task_id": build_task.id,
            "status": "done",
            "stats": {},
            "artifacts": [
                {
                    "name": name,
                    "type": "rpm",
                    "href": get_artifact_href(),
                    "sha256": hashlib.sha256().hexdigest(),
                }
                for name in (
                    "go-toolset-1.18.9-1.module_el8.7.0+3397+4350156d.src.rpm",
                    f"go-toolset-1.18.9-1.module_el8.7.0+3397+4350156d.{build_task.arch}.rpm",
                )
            ],
        }
        await safe_build_done(session, BuildDone(**payload))

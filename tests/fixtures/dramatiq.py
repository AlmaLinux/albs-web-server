import hashlib
import typing

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from alws.crud.build import get_builds
from alws.crud.build_node import safe_build_done
from alws.dramatiq.build import _start_build
from alws.models import Build
from alws.schemas.build_node_schema import BuildDone
from alws.schemas.build_schema import BuildCreate
from tests.test_utils.pulp_utils import get_artifact_href
from alws.constants import BuildTaskStatus


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
async def start_modular_virt_build(
    virt_modular_build: Build,
    virt_build_payload: dict,
    create_virt_module,
    create_build_rpm_repo,
    create_log_repo,
    modify_repository,
):
    await _start_build(
        virt_modular_build.id,
        BuildCreate(**virt_build_payload),
    )


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


def prepare_build_done_payload(
    task_id: str,
    packages: typing.List[str],
    status: str = "done",    
):
    return {
        'task_id': task_id,
        'status': status,
        'stats': {},
        'artifacts': [
            {
                'name': name,
                'type': 'rpm',
                'href': get_artifact_href(),
                'sha256': hashlib.sha256().hexdigest(),
            }
            for name in packages
        ],
    }


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
        await safe_build_done(
            session,
            BuildDone(
                **prepare_build_done_payload(
                    build_task.id,
                    [
                        "chan-0.0.4-3.el8.src.rpm",
                        f"chan-0.0.4-3.el8.{build_task.arch}.rpm",
                    ],
                )
            ),
        )


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
        await safe_build_done(
            session,
            BuildDone(
                **prepare_build_done_payload(
                    build_task.id,
                    [
                        "go-toolset-1.18.9-1.module_el8.7.0+3397+4350156d.src.rpm",
                        f"go-toolset-1.18.9-1.module_el8.7.0+3397+4350156d.{build_task.arch}.rpm",
                    ],
                )
            ),
        )


@pytest.mark.anyio
@pytest.fixture
async def virt_build_done(
    session: AsyncSession,
    virt_modular_build: Build,
    modify_repository,
    start_modular_virt_build,
    create_entity,
    get_rpm_packages_info,
    get_repo_virt_modules_yaml,
    get_repo_modules,
):
    build = await get_builds(db=session, build_id=virt_modular_build.id)
    await session.close()
    for build_task in build.tasks:
        status="done"
        packages = []
        if "hivex" in build_task.ref.url:
            packages = [
                "hivex-1.3.18-23.module_el8.6.0+2880+7d9e3703.src.rpm",
                f'hivex-1.3.18-23.module_el8.6.0+2880+7d9e3703.{build_task.arch}.rpm',
                f'hivex-debuginfo-1.3.18-23.module_el8.6.0+2880+7d9e3703.{build_task.arch}.rpm',
                f'hivex-debugsource-1.3.18-23.module_el8.6.0+2880+7d9e3703.{build_task.arch}.rpm',
                f'hivex-devel-1.3.18-23.module_el8.6.0+2880+7d9e3703.{build_task.arch}.rpm',
                f'ocaml-hivex-1.3.18-23.module_el8.6.0+2880+7d9e3703.{build_task.arch}.rpm',
                f'ocaml-hivex-devel-1.3.18-23.module_el8.6.0+2880+7d9e3703.{build_task.arch}.rpm',
                f'ocaml-hivex-debuginfo-1.3.18-23.module_el8.6.0+2880+7d9e3703.{build_task.arch}.rpm',
            ]
        if "qemu" in build_task.ref.url:
            packages = ["qemu-kvm-6.2.0-32.module_el8.8.0+3553+bd08596b.src.rpm"]
            if build_task.arch == "i686":
                status = "excluded"
            else:
                packages.extend([
                    f'qemu-kvm-6.2.0-32.module_el8.8.0+3553+bd08596b.{build_task.arch}.rpm',
                    f'qemu-kvm-debugsource-6.2.0-32.module_el8.8.0+3553+bd08596b.{build_task.arch}.rpm',
                    f'qemu-kvm-debuginfo-6.2.0-32.module_el8.8.0+3553+bd08596b.{build_task.arch}.rpm',
                ])
        if "SLOF" in build_task.ref.url:
            packages = ["SLOF-20210217-1.module_el8.6.0+2880+7d9e3703.src.rpm"]
            if build_task.arch == "ppc64le":
                packages.append(
                    "SLOF-20210217-1.module_el8.6.0+2880+7d9e3703.noarch.rpm"
                )
            else:
                status="excluded"

        await safe_build_done(
            session,
            BuildDone(**prepare_build_done_payload(
                build_task.id,
                packages,
                status=status,
            )),
        )

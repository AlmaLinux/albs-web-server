import hashlib
import typing

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from alws.constants import BuildTaskStatus
from alws.crud import test
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
async def start_modular_virt_build(
    virt_modular_build: Build,
    virt_build_payload: dict,
    create_multilib_module,
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
async def start_modular_ruby_build(
    ruby_modular_build: Build,
    ruby_build_payload: dict,
    create_multilib_module,
    create_build_rpm_repo,
    create_log_repo,
    modify_repository,
):
    await _start_build(
        ruby_modular_build.id,
        BuildCreate(**ruby_build_payload),
    )


@pytest.mark.anyio
@pytest.fixture
async def start_modular_subversion_build(
    subversion_modular_build: Build,
    subversion_build_payload: dict,
    create_multilib_module,
    create_build_rpm_repo,
    create_log_repo,
    modify_repository,
):
    await _start_build(
        subversion_modular_build.id,
        BuildCreate(**subversion_build_payload),
    )


@pytest.mark.anyio
@pytest.fixture
async def start_modular_llvm_build(
    llvm_modular_build: Build,
    llvm_build_payload: dict,
    create_multilib_module,
    create_build_rpm_repo,
    create_log_repo,
    modify_repository,
):
    await _start_build(
        llvm_modular_build.id,
        BuildCreate(**llvm_build_payload),
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
    async_session: AsyncSession,
    regular_build: Build,
    start_build,
    create_entity,
    get_rpm_packages_info,
    mock_get_pulp_packages,
    get_packages_info_from_pulp,
):
    build = await get_builds(db=async_session, build_id=regular_build.id)
    await async_session.close()
    for build_task in build.tasks:
        await safe_build_done(
            async_session,
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
        await async_session.commit()
    build = await get_builds(db=async_session, build_id=regular_build.id)
    for build_task in build.tasks:
        assert build_task.status == BuildTaskStatus.COMPLETED
    await async_session.close()
    await test.create_test_tasks_for_build_id(async_session, build.id)
    await async_session.commit()


@pytest.mark.anyio
@pytest.fixture
async def modular_build_done(
    async_session: AsyncSession,
    modular_build: Build,
    start_modular_build,
    create_entity,
    get_rpm_packages_info,
    get_repo_modules_yaml,
    get_repo_modules,
):
    build = await get_builds(db=async_session, build_id=modular_build.id)
    await async_session.close()
    for build_task in build.tasks:
        await safe_build_done(
            async_session,
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
    await async_session.commit()


@pytest.mark.anyio
@pytest.fixture
async def virt_build_done(
    async_session: AsyncSession,
    virt_modular_build: Build,
    modify_repository,
    start_modular_virt_build,
    create_entity,
    get_rpm_packages_info,
    get_repo_virt_modules_yaml,
    get_repo_modules,
):
    build = await get_builds(db=async_session, build_id=virt_modular_build.id)
    await async_session.close()
    for build_task in build.tasks:
        status = "done"
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
            packages = [
                "qemu-kvm-6.2.0-32.module_el8.8.0+3553+bd08596b.src.rpm"
            ]
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
                status = "excluded"

        await safe_build_done(
            async_session,
            BuildDone(
                **prepare_build_done_payload(
                    build_task.id,
                    packages,
                    status=status,
                )
            ),
        )
    await async_session.commit()


@pytest.mark.anyio
@pytest.fixture
async def ruby_build_done(
    async_session: AsyncSession,
    ruby_modular_build: Build,
    modify_repository,
    start_modular_ruby_build,
    create_entity,
    get_rpm_packages_info,
    get_repo_ruby_modules_yaml,
    get_repo_modules,
):
    build = await get_builds(db=async_session, build_id=ruby_modular_build.id)
    await async_session.close()
    for build_task in build.tasks:
        packages = [
            "ruby-3.1.2-141.module_el8.1.0+8+503f6fbd.src.rpm",
            f"ruby-3.1.2-141.module_el8.1.0+8+503f6fbd.{build_task.arch}.rpm",
            f"ruby-devel-3.1.2-141.module_el8.1.0+8+503f6fbd.{build_task.arch}.rpm",
            f"ruby-debugsource-3.1.2-141.module_el8.1.0+8+503f6fbd.{build_task.arch}.rpm",
            f"ruby-debuginfo-3.1.2-141.module_el8.1.0+8+503f6fbd.{build_task.arch}.rpm",
            "rubygems-3.3.7-141.module_el8.1.0+8+503f6fbd.noarch.rpm",
            "rubygems-devel-3.3.7-141.module_el8.1.0+8+503f6fbd.noarch.rpm",
        ]
        if "rubygem-pg" in build_task.ref.url:
            packages = [
                "rubygem-pg-1.3.5-1.module_el8.1.0+8+503f6fbd.src.rpm",
                f"rubygem-pg-1.3.5-1-141.module_el8.1.0+8+503f6fbd.{build_task.arch}.rpm",
                f"rubygem-pg-debugsource-3.1.2-141.module_el8.1.0+8+503f6fbd.{build_task.arch}.rpm",
                f"rubygem-pg-debuginfo-3.1.2-141.module_el8.1.0+8+503f6fbd.{build_task.arch}.rpm",
                "rubygem-pg-doc-3.3.7-141.module_el8.1.0+8+503f6fbd.noarch.rpm",
            ]
        await safe_build_done(
            async_session,
            BuildDone(**prepare_build_done_payload(build_task.id, packages)),
        )
    await async_session.commit()


@pytest.mark.anyio
@pytest.fixture
async def subversion_build_done(
    async_session: AsyncSession,
    subversion_modular_build: Build,
    modify_repository,
    start_modular_subversion_build,
    create_entity,
    get_rpm_packages_info,
    get_repo_subversion_modules_yaml,
    get_repo_modules,
):
    build = await get_builds(
        db=async_session, build_id=subversion_modular_build.id
    )
    await async_session.close()
    for build_task in build.tasks:
        packages = [
            "subversion-1.10.2-5.module_el8.6.0+3347+66c1e1d6.src.rpm",
            f"subversion-1.10.2-5.module_el8.6.0+3347+66c1e1d6.{build_task.arch}.rpm",
            f"subversion-debuginfo-1.10.2-5.module_el8.6.0+3347+66c1e1d6.{build_task.arch}.rpm",
            f"subversion-debugsource-1.10.2-5.module_el8.6.0+3347+66c1e1d6.{build_task.arch}.rpm",
            f"subversion-devel-1.10.2-5.module_el8.6.0+3347+66c1e1d6.{build_task.arch}.rpm",
            f"subversion-ruby-1.10.2-5.module_el8.6.0+3347+66c1e1d6.{build_task.arch}.rpm",
        ]
        await safe_build_done(
            async_session,
            BuildDone(**prepare_build_done_payload(build_task.id, packages)),
        )
    await async_session.commit()


@pytest.mark.anyio
@pytest.fixture
async def llvm_build_done(
    async_session: AsyncSession,
    llvm_modular_build: Build,
    modify_repository,
    start_modular_llvm_build,
    create_entity,
    get_rpm_packages_info,
    get_repo_llvm_modules_yaml,
    get_repo_modules,
):
    build = await get_builds(db=async_session, build_id=llvm_modular_build.id)
    await async_session.close()
    for build_task in build.tasks:
        packages = []
        if "python" in build_task.ref.url:
            packages = [
                "python-lit-13.0.1-1.module+el8.6.0+14118+d530a951.src.rpm",
                "python3-lit-13.0.1-1.module+el8.6.0+14118+d530a951.noarch.rpm",
            ]
        if "llvm" in build_task.ref.url:
            packages = [
                "llvm-13.0.1-1.module+el8.6.0+14118+d530a951.src.rpm",
                f"llvm-13.0.1-1.module+el8.6.0+14118+d530a951.{build_task.arch}.rpm",
            ]
        await safe_build_done(
            async_session,
            BuildDone(**prepare_build_done_payload(build_task.id, packages)),
        )
    await async_session.commit()

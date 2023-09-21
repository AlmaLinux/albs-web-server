import copy
import typing

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from alws.crud.build import create_build, get_builds
from alws.dramatiq.build import _start_build
from alws.models import Build, Product
from alws.schemas.build_schema import BuildCreate
from tests.constants import ADMIN_USER_ID
from tests.test_utils.pulp_utils import get_rpm_pkg_info


@pytest.fixture(
    params=[
        [],
        [
            {
                "url": "https://git.almalinux.org/rpms/go-toolset.git",
                "git_ref": "c8-stream-rhel8",
                "exist": True,
                "enabled": False,
                "added_artifacts": [],
                "mock_options": {
                    "definitions": {},
                    "module_enable": [
                        "go-toolset:rhel8",
                        "go-toolset-devel:rhel8",
                    ],
                },
                "ref_type": 1,
            },
            {
                "url": "https://git.almalinux.org/rpms/golang.git",
                "git_ref": "c8-stream-rhel8",
                "exist": True,
                "enabled": False,
                "added_artifacts": [],
                "mock_options": {
                    "definitions": {},
                    "module_enable": [
                        "go-toolset:rhel8",
                        "go-toolset-devel:rhel8",
                    ],
                },
                "ref_type": 1,
            },
            {
                "url": "https://git.almalinux.org/rpms/delve.git",
                "git_ref": "c8-stream-rhel8",
                "exist": True,
                "enabled": False,
                "added_artifacts": [],
                "mock_options": {
                    "definitions": {},
                    "module_enable": [
                        "go-toolset:rhel8",
                        "go-toolset-devel:rhel8",
                    ],
                },
                "ref_type": 1,
            },
        ],
    ],
    ids=[
        "empty_refs",
        "only_disabled_refs",
    ],
)
def nonvalid_modular_build_payload(request) -> typing.Dict[str, typing.Any]:
    return {
        "platforms": [
            {
                "name": "AlmaLinux-8",
                "arch_list": ["i686", "x86_64"],
                "parallel_mode_enabled": True,
            }
        ],
        "tasks": [
            {
                "refs": request.param,
                "modules_yaml": '---\ndocument: modulemd\nversion: 2\ndata:\n  name: go-toolset\n  stream: "rhel8"\n  arch: x86_64\n  summary: Go\n  description: >-\n    Go Tools and libraries\n  license:\n    module:\n    - MIT\n  dependencies:\n  - buildrequires:\n      go-toolset: [rhel8]\n      platform: [el8]\n    requires:\n      platform: [el8]\n  profiles:\n    common:\n      rpms:\n      - go-toolset\n  api:\n    rpms:\n    - golang\n  buildopts:\n    rpms:\n      whitelist:\n      - delve\n      - go-toolset\n      - go-toolset-1.10\n      - go-toolset-1.10-golang\n      - go-toolset-golang\n      - golang\n  components:\n    rpms:\n      delve:\n        rationale: A debugger for the Go programming language\n        ref: 18f55f0e6d4d9579ac949e3a96c1c2f6e877cba8\n        buildorder: 2\n      go-toolset:\n        rationale: Meta package for go-toolset providing scl enable scripts.\n        ref: feda7855f214faf3cbb4324c74a47e4a00d117a8\n      golang:\n        rationale: Package providing the Go compiler toolchain.\n        ref: 61d02fbf0e5553e82c220cfb2f403338f43496b6\n        buildorder: 1\n...\n\n---\ndocument: modulemd\nversion: 2\ndata:\n  name: go-toolset-devel\n  stream: "rhel8"\n  summary: Go\n  description: >-\n    Go Tools and libraries\n  license:\n    module:\n    - MIT\n  dependencies:\n  - buildrequires:\n      go-toolset: [rhel8]\n      platform: [el8]\n    requires:\n      platform: [el8]\n  profiles:\n    common:\n      rpms:\n      - go-toolset\n  api:\n    rpms:\n    - golang\n  buildopts:\n    rpms:\n      whitelist:\n      - delve\n      - go-toolset\n      - go-toolset-1.10\n      - go-toolset-1.10-golang\n      - go-toolset-golang\n      - golang\n  components:\n    rpms:\n      delve:\n        rationale: A debugger for the Go programming language\n        ref: 18f55f0e6d4d9579ac949e3a96c1c2f6e877cba8\n        buildorder: 2\n      go-toolset:\n        rationale: Meta package for go-toolset providing scl enable scripts.\n        ref: feda7855f214faf3cbb4324c74a47e4a00d117a8\n      golang:\n        rationale: Package providing the Go compiler toolchain.\n        ref: 61d02fbf0e5553e82c220cfb2f403338f43496b6\n        buildorder: 1\n...\n',
                "module_name": "go-toolset",
                "module_stream": "rhel8",
                "enabled_modules": {"buildtime": [], "runtime": []},
                "git_ref": "c8-stream-rhel8",
                "module_platform_version": "8.6",
                "enabled_modules_table": [
                    {
                        "name": "go-toolset",
                        "stream": "rhel8",
                        "main": True,
                        "enable": True,
                    },
                    {
                        "name": "go-toolset-devel",
                        "stream": "rhel8",
                        "main": True,
                        "enable": True,
                    },
                ],
                "selectedModules": {},
            }
        ],
        "linked_builds": [],
        "is_secure_boot": False,
        "mock_options": {},
        "platform_flavors": [],
        "product_id": 1,
    }


@pytest.fixture
def modular_build_payload() -> typing.Dict[str, typing.Any]:
    return {
        "platforms": [
            {
                "name": "AlmaLinux-8",
                "arch_list": ["i686", "x86_64"],
                "parallel_mode_enabled": True,
            }
        ],
        "tasks": [
            {
                "refs": [
                    {
                        "url": "https://git.almalinux.org/rpms/go-toolset.git",
                        "git_ref": "c8-stream-rhel8",
                        "exist": True,
                        "enabled": True,
                        "added_artifacts": [],
                        "mock_options": {
                            "definitions": {},
                            "module_enable": [
                                "go-toolset:rhel8",
                                "go-toolset-devel:rhel8",
                            ],
                        },
                        "ref_type": 1,
                    },
                    {
                        "url": "https://git.almalinux.org/rpms/golang.git",
                        "git_ref": "c8-stream-rhel8",
                        "exist": True,
                        "enabled": True,
                        "added_artifacts": [],
                        "mock_options": {
                            "definitions": {},
                            "module_enable": [
                                "go-toolset:rhel8",
                                "go-toolset-devel:rhel8",
                            ],
                        },
                        "ref_type": 1,
                    },
                    {
                        "url": "https://git.almalinux.org/rpms/delve.git",
                        "git_ref": "c8-stream-rhel8",
                        "exist": True,
                        "enabled": True,
                        "added_artifacts": [],
                        "mock_options": {
                            "definitions": {},
                            "module_enable": [
                                "go-toolset:rhel8",
                                "go-toolset-devel:rhel8",
                            ],
                        },
                        "ref_type": 1,
                    },
                ],
                "modules_yaml": '---\ndocument: modulemd\nversion: 2\ndata:\n  name: go-toolset\n  stream: "rhel8"\n  arch: x86_64\n  summary: Go\n  description: >-\n    Go Tools and libraries\n  license:\n    module:\n    - MIT\n  dependencies:\n  - buildrequires:\n      go-toolset: [rhel8]\n      platform: [el8]\n    requires:\n      platform: [el8]\n  profiles:\n    common:\n      rpms:\n      - go-toolset\n  api:\n    rpms:\n    - golang\n  buildopts:\n    rpms:\n      whitelist:\n      - delve\n      - go-toolset\n      - go-toolset-1.10\n      - go-toolset-1.10-golang\n      - go-toolset-golang\n      - golang\n  components:\n    rpms:\n      delve:\n        rationale: A debugger for the Go programming language\n        ref: 18f55f0e6d4d9579ac949e3a96c1c2f6e877cba8\n        buildorder: 2\n      go-toolset:\n        rationale: Meta package for go-toolset providing scl enable scripts.\n        ref: feda7855f214faf3cbb4324c74a47e4a00d117a8\n      golang:\n        rationale: Package providing the Go compiler toolchain.\n        ref: 61d02fbf0e5553e82c220cfb2f403338f43496b6\n        buildorder: 1\n...\n\n---\ndocument: modulemd\nversion: 2\ndata:\n  name: go-toolset-devel\n  stream: "rhel8"\n  summary: Go\n  description: >-\n    Go Tools and libraries\n  license:\n    module:\n    - MIT\n  dependencies:\n  - buildrequires:\n      go-toolset: [rhel8]\n      platform: [el8]\n    requires:\n      platform: [el8]\n  profiles:\n    common:\n      rpms:\n      - go-toolset\n  api:\n    rpms:\n    - golang\n  buildopts:\n    rpms:\n      whitelist:\n      - delve\n      - go-toolset\n      - go-toolset-1.10\n      - go-toolset-1.10-golang\n      - go-toolset-golang\n      - golang\n  components:\n    rpms:\n      delve:\n        rationale: A debugger for the Go programming language\n        ref: 18f55f0e6d4d9579ac949e3a96c1c2f6e877cba8\n        buildorder: 2\n      go-toolset:\n        rationale: Meta package for go-toolset providing scl enable scripts.\n        ref: feda7855f214faf3cbb4324c74a47e4a00d117a8\n      golang:\n        rationale: Package providing the Go compiler toolchain.\n        ref: 61d02fbf0e5553e82c220cfb2f403338f43496b6\n        buildorder: 1\n...\n',
                "module_name": "go-toolset",
                "module_stream": "rhel8",
                "enabled_modules": {"buildtime": [], "runtime": []},
                "git_ref": "c8-stream-rhel8",
                "module_platform_version": "8.6",
                "enabled_modules_table": [
                    {
                        "name": "go-toolset",
                        "stream": "rhel8",
                        "main": True,
                        "enable": True,
                    },
                    {
                        "name": "go-toolset-devel",
                        "stream": "rhel8",
                        "main": True,
                        "enable": True,
                    },
                ],
                "selectedModules": {},
            }
        ],
        "linked_builds": [],
        "is_secure_boot": False,
        "mock_options": {},
        "platform_flavors": [],
        "product_id": 1,
    }


@pytest.fixture
def virt_build_payload():
    return {
        "platforms": [
            {
                "name": "AlmaLinux-8",
                "arch_list": ["i686", "x86_64", "ppc64le"],
                "parallel_mode_enabled": True,
            }
        ],
        "tasks": [
            {
                "refs": [
                    {
                        "url": "https://git.almalinux.org/rpms/SLOF.git",
                        "git_ref": "c8-stream-rhel",
                        "exist": True,
                        "enabled": True,
                        "added_artifacts": [],
                        "mock_options": {
                            "definitions": {},
                            "module_enable": ["virt:rhel", "virt-devel:rhel"],
                        },
                        "ref_type": 1,
                    },
                    {
                        "url": "https://git.almalinux.org/rpms/hivex.git",
                        "git_ref": "c8-stream-rhel",
                        "exist": True,
                        "enabled": True,
                        "added_artifacts": [],
                        "mock_options": {
                            "definitions": {},
                            "module_enable": ["virt:rhel", "virt-devel:rhel"],
                        },
                        "ref_type": 1,
                    },
                    {
                        "url": "https://git.almalinux.org/rpms/qemu-kvm.git",
                        "git_ref": "c8-stream-rhel",
                        "exist": True,
                        "enabled": True,
                        "added_artifacts": [],
                        "mock_options": {
                            "definitions": {},
                            "module_enable": ["virt:rhel", "virt-devel:rhel"],
                        },
                        "ref_type": 1,
                    },
                ],
                "modules_yaml": "---\ndocument: modulemd\nversion: 2\ndata:\n  name: virt\n  stream: \"rhel\"\n  summary: Virtualization module\n  description: >-\n    A virtualization module\n  license:\n    module:\n    - MIT\n  dependencies:\n  - buildrequires:\n      platform: [el8]\n    requires:\n      platform: [el8]\n  profiles:\n    common:\n      rpms:\n      - libguestfs\n      - libvirt-client\n      - libvirt-daemon-config-network\n      - libvirt-daemon-kvm\n  filter:\n    rpms:\n    - ocaml-hivex\n    - ocaml-hivex-debuginfo\n    - ocaml-hivex-devel\n    - ocaml-libguestfs\n    - ocaml-libguestfs-debuginfo\n    - ocaml-libguestfs-devel\n    - ocaml-libnbd\n    - ocaml-libnbd-debuginfo\n    - ocaml-libnbd-devel\n    - qemu-kvm-tests\n    - qemu-kvm-tests-debuginfo\n  components:\n    rpms:\n      SLOF:\n        rationale: qemu-kvm dep\n        ref: dbd7d071c75dcc732c933f451e4b6dbc4a72b783\n        buildorder: 1\n        arches: [ppc64le]\n      hivex:\n        rationale: libguestfs dep\n        ref: 3b801940c0f8c11129805fe59590e0ee3aabb608\n        buildorder: 1\n      libguestfs:\n        rationale: Primary module content\n        ref: 61243f50c78c87d92728017318f2c1ff16d02635\n        buildorder: 4\n      libguestfs-winsupport:\n        rationale: Primary module content\n        ref: 3ea195ba2c089522b83479738a54b7e879d3eb79\n        buildorder: 5\n      libiscsi:\n        rationale: qemu-kvm dep\n        ref: 03c364210208727e90e1fa6b1fdf2cb8a5040991\n        buildorder: 1\n      libnbd:\n        rationale: Primary module content\n        ref: 951092b53e6ed1bc9eed1b29df803595d91a2c7f\n        buildorder: 1\n      libtpms:\n        rationale: Primary module content\n        ref: 86b8f6f47dc6b39d2484bb5a506f088dab36eee2\n        buildorder: 1\n      libvirt:\n        rationale: Primary module content\n        ref: 722e8085db76a4334d6eac2a4668ce0a24bb6bbd\n        buildorder: 3\n      libvirt-dbus:\n        rationale: libvirt-dbus is part of the virtualization module\n        ref: 4a1caa1b08966a6cfcf4860c12bf61ec54cd74d3\n        buildorder: 4\n      libvirt-python:\n        rationale: Primary module content\n        ref: 062f06a46bae3b6b75fdf86cdec07eed6845f85f\n        buildorder: 4\n      nbdkit:\n        rationale: Primary module content\n        ref: 317a0878c7849f4eabe3965a83734d3f5ba8ee41\n        buildorder: 5\n      netcf:\n        rationale: libvirt dep\n        ref: 9cafbecc76f1f51c6349c46cc0765e6c6ea9997f\n        buildorder: 1\n      perl-Sys-Virt:\n        rationale: Primary module content\n        ref: 7e16e8f82d470412e6d8fe58daed83c1470d599e\n        buildorder: 4\n      qemu-kvm:\n        rationale: Primary module content\n        ref: 9cf15efa745c2df3f2968d58da9ed67b29b1300f\n        buildorder: 2\n      seabios:\n        rationale: qemu-kvm dep\n        ref: 94f4f45b8837c5e834b0ae11d368978c621c6fbc\n        buildorder: 1\n        arches: [ppc64le, x86_64]\n      sgabios:\n        rationale: qemu-kvm dep\n        ref: 643ad1528f18937fa5fa0a021a8f25dd1e252596\n        buildorder: 1\n        arches: [ppc64le, x86_64]\n      supermin:\n        rationale: libguestfs dep\n        ref: 502fabee05eb11c69d2fe29becf23e0e013a1995\n        buildorder: 2\n      swtpm:\n        rationale: Primary module content\n        ref: 12e26459a3feb201950bf8d52a9af95afd601a5b\n        buildorder: 2\n      virt-v2v:\n        rationale: Primary module content\n        ref: 22c887f059f0127d58f53e1d00b38c297e565890\n        buildorder: 6\n...\n\n---\ndocument: modulemd\nversion: 2\ndata:\n  name: virt-devel\n  stream: \"rhel\"\n  summary: Virtualization module\n  description: >-\n    A virtualization module\n  license:\n    module:\n    - MIT\n  dependencies:\n  - buildrequires:\n      platform: [el8]\n    requires:\n      platform: [el8]\n  profiles:\n    common:\n      rpms:\n      - libguestfs\n      - libvirt-client\n      - libvirt-daemon-config-network\n      - libvirt-daemon-kvm\n  filter:\n    rpms:\n    - ocaml-hivex\n    - ocaml-hivex-debuginfo\n    - ocaml-hivex-devel\n    - ocaml-libguestfs\n    - ocaml-libguestfs-debuginfo\n    - ocaml-libguestfs-devel\n    - ocaml-libnbd\n    - ocaml-libnbd-debuginfo\n    - ocaml-libnbd-devel\n    - qemu-kvm-tests\n    - qemu-kvm-tests-debuginfo\n  components:\n    rpms:\n      SLOF:\n        rationale: qemu-kvm dep\n        ref: dbd7d071c75dcc732c933f451e4b6dbc4a72b783\n        buildorder: 1\n        arches: [ppc64le]\n      hivex:\n        rationale: libguestfs dep\n        ref: 3b801940c0f8c11129805fe59590e0ee3aabb608\n        buildorder: 1\n      libguestfs:\n        rationale: Primary module content\n        ref: 61243f50c78c87d92728017318f2c1ff16d02635\n        buildorder: 4\n      libguestfs-winsupport:\n        rationale: Primary module content\n        ref: 3ea195ba2c089522b83479738a54b7e879d3eb79\n        buildorder: 5\n      libiscsi:\n        rationale: qemu-kvm dep\n        ref: 03c364210208727e90e1fa6b1fdf2cb8a5040991\n        buildorder: 1\n      libnbd:\n        rationale: Primary module content\n        ref: 951092b53e6ed1bc9eed1b29df803595d91a2c7f\n        buildorder: 1\n      libtpms:\n        rationale: Primary module content\n        ref: 86b8f6f47dc6b39d2484bb5a506f088dab36eee2\n        buildorder: 1\n      libvirt:\n        rationale: Primary module content\n        ref: 722e8085db76a4334d6eac2a4668ce0a24bb6bbd\n        buildorder: 3\n      libvirt-dbus:\n        rationale: libvirt-dbus is part of the virtualization module\n        ref: 4a1caa1b08966a6cfcf4860c12bf61ec54cd74d3\n        buildorder: 4\n      libvirt-python:\n        rationale: Primary module content\n        ref: 062f06a46bae3b6b75fdf86cdec07eed6845f85f\n        buildorder: 4\n      nbdkit:\n        rationale: Primary module content\n        ref: 317a0878c7849f4eabe3965a83734d3f5ba8ee41\n        buildorder: 5\n      netcf:\n        rationale: libvirt dep\n        ref: 9cafbecc76f1f51c6349c46cc0765e6c6ea9997f\n        buildorder: 1\n      perl-Sys-Virt:\n        rationale: Primary module content\n        ref: 7e16e8f82d470412e6d8fe58daed83c1470d599e\n        buildorder: 4\n      qemu-kvm:\n        rationale: Primary module content\n        ref: 9cf15efa745c2df3f2968d58da9ed67b29b1300f\n        buildorder: 2\n      seabios:\n        rationale: qemu-kvm dep\n        ref: 94f4f45b8837c5e834b0ae11d368978c621c6fbc\n        buildorder: 1\n        arches: [ppc64le, x86_64]\n      sgabios:\n        rationale: qemu-kvm dep\n        ref: 643ad1528f18937fa5fa0a021a8f25dd1e252596\n        buildorder: 1\n        arches: [ppc64le, x86_64]\n      supermin:\n        rationale: libguestfs dep\n        ref: 502fabee05eb11c69d2fe29becf23e0e013a1995\n        buildorder: 2\n      swtpm:\n        rationale: Primary module content\n        ref: 12e26459a3feb201950bf8d52a9af95afd601a5b\n        buildorder: 2\n      virt-v2v:\n        rationale: Primary module content\n        ref: 22c887f059f0127d58f53e1d00b38c297e565890\n        buildorder: 6\n...\n",
                "module_name": "virt",
                "module_stream": "rhel",
                "enabled_modules": {"buildtime": [], "runtime": []},
                "git_ref": "c8-stream-rhel",
                "module_platform_version": "8.6",
                "enabled_modules_table": [
                    {
                        "name": "virt",
                        "stream": "rhel",
                        "main": True,
                        "enable": True,
                    },
                    {
                        "name": "virt-devel",
                        "stream": "rhel",
                        "main": True,
                        "enable": True,
                    },
                ],
                "selectedModules": {},
            }
        ],
        "linked_builds": [],
        "is_secure_boot": False,
        "mock_options": {},
        "platform_flavors": [],
        "product_id": 1,
    }


@pytest.fixture
def build_payload() -> typing.Dict[str, typing.Any]:
    return {
        "platforms": [
            {
                "name": "AlmaLinux-8",
                "arch_list": ["i686", "x86_64"],
                "parallel_mode_enabled": True,
            }
        ],
        "tasks": [
            {
                "git_ref": "c8",
                "url": "https://git.almalinux.org/rpms/chan.git",
                "ref_type": 4,
                "mock_options": {},
            }
        ],
        "linked_builds": [],
        "is_secure_boot": False,
        "mock_options": {},
        "platform_flavors": [],
        "product_id": 1,
    }


@pytest.mark.anyio
@pytest.fixture
async def modular_build(
    session: AsyncSession,
    modular_build_payload: dict,
) -> typing.AsyncIterable[Build]:
    yield await create_build(
        session,
        BuildCreate(**modular_build_payload),
        user_id=ADMIN_USER_ID,
    )


@pytest.mark.anyio
@pytest.fixture
async def virt_modular_build(
    session: AsyncSession,
    virt_build_payload: dict,
) -> typing.AsyncIterable:
    yield await create_build(
        session,
        BuildCreate(**virt_build_payload),
        user_id=ADMIN_USER_ID,
    )


@pytest.mark.anyio
@pytest.fixture
async def regular_build(
    session: AsyncSession,
    build_payload: dict,
) -> typing.AsyncIterable[Build]:
    yield await create_build(
        session,
        BuildCreate(**build_payload),
        user_id=ADMIN_USER_ID,
    )


@pytest.mark.anyio
@pytest.fixture
async def regular_build_with_user_product(
    session: AsyncSession,
    build_payload: dict,
    create_build_rpm_repo,
    create_log_repo,
    modify_repository,
) -> typing.AsyncIterable[Build]:
    payload = copy.deepcopy(build_payload)
    user_product_id = (
        (
            await session.execute(
                select(Product.id).where(Product.is_community.is_(True))
            )
        )
        .scalars()
        .first()
    )
    payload['product_id'] = user_product_id
    build = await create_build(
        session,
        BuildCreate(**payload),
        user_id=ADMIN_USER_ID,
    )
    await _start_build(build.id, BuildCreate(**payload))
    yield await get_builds(session, build_id=build.id)


@pytest.fixture
def get_rpm_packages_info(monkeypatch):
    def func(artifacts):
        return {
            artifact.href: get_rpm_pkg_info(artifact) for artifact in artifacts
        }

    monkeypatch.setattr("alws.crud.build_node.get_rpm_packages_info", func)


@pytest.mark.anyio
@pytest.fixture
async def build_for_release(
    session: AsyncSession,
    regular_build: Build,
) -> typing.AsyncIterable[Build]:
    yield await get_builds(session, build_id=regular_build.id)


@pytest.mark.anyio
@pytest.fixture
async def modular_build_for_release(
    session: AsyncSession,
    modular_build: Build,
) -> typing.AsyncIterable[Build]:
    yield await get_builds(session, build_id=modular_build.id)

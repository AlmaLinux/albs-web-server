import copy
import typing

import pytest
from fastapi_sqla import open_async_session
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm.session import Session

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
        "platforms": [{
            "name": "AlmaLinux-8",
            "arch_list": ["i686", "x86_64"],
            "parallel_mode_enabled": True,
        }],
        "tasks": [{
            "refs": request.param,
            "modules_yaml": (
                '---\ndocument: modulemd\nversion: 2\ndata:\n  name:'
                ' go-toolset\n  stream: "rhel8"\n  arch: x86_64\n '
                ' summary: Go\n  description: >-\n    Go Tools and'
                ' libraries\n  license:\n    module:\n    - MIT\n '
                ' dependencies:\n  - buildrequires:\n      go-toolset:'
                ' [rhel8]\n      platform: [el8]\n    requires:\n     '
                ' platform: [el8]\n  profiles:\n    common:\n      rpms:\n'
                '      - go-toolset\n  api:\n    rpms:\n    - golang\n '
                ' buildopts:\n    rpms:\n      whitelist:\n      - delve\n'
                '      - go-toolset\n      - go-toolset-1.10\n      -'
                ' go-toolset-1.10-golang\n      - go-toolset-golang\n     '
                ' - golang\n  components:\n    rpms:\n      delve:\n      '
                '  rationale: A debugger for the Go programming language\n'
                '        ref: 18f55f0e6d4d9579ac949e3a96c1c2f6e877cba8\n  '
                '      buildorder: 2\n      go-toolset:\n       '
                ' rationale: Meta package for go-toolset providing scl'
                ' enable scripts.\n        ref:'
                ' feda7855f214faf3cbb4324c74a47e4a00d117a8\n     '
                ' golang:\n        rationale: Package providing the Go'
                ' compiler toolchain.\n        ref:'
                ' 61d02fbf0e5553e82c220cfb2f403338f43496b6\n       '
                ' buildorder: 1\n...\n\n---\ndocument: modulemd\nversion:'
                ' 2\ndata:\n  name: go-toolset-devel\n  stream: "rhel8"\n '
                ' summary: Go\n  description: >-\n    Go Tools and'
                ' libraries\n  license:\n    module:\n    - MIT\n '
                ' dependencies:\n  - buildrequires:\n      go-toolset:'
                ' [rhel8]\n      platform: [el8]\n    requires:\n     '
                ' platform: [el8]\n  profiles:\n    common:\n      rpms:\n'
                '      - go-toolset\n  api:\n    rpms:\n    - golang\n '
                ' buildopts:\n    rpms:\n      whitelist:\n      - delve\n'
                '      - go-toolset\n      - go-toolset-1.10\n      -'
                ' go-toolset-1.10-golang\n      - go-toolset-golang\n     '
                ' - golang\n  components:\n    rpms:\n      delve:\n      '
                '  rationale: A debugger for the Go programming language\n'
                '        ref: 18f55f0e6d4d9579ac949e3a96c1c2f6e877cba8\n  '
                '      buildorder: 2\n      go-toolset:\n       '
                ' rationale: Meta package for go-toolset providing scl'
                ' enable scripts.\n        ref:'
                ' feda7855f214faf3cbb4324c74a47e4a00d117a8\n     '
                ' golang:\n        rationale: Package providing the Go'
                ' compiler toolchain.\n        ref:'
                ' 61d02fbf0e5553e82c220cfb2f403338f43496b6\n       '
                ' buildorder: 1\n...\n'
            ),
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
        }],
        "linked_builds": [],
        "is_secure_boot": False,
        "mock_options": {},
        "platform_flavors": [],
        "product_id": 1,
    }


@pytest.fixture
def modular_build_payload() -> typing.Dict[str, typing.Any]:
    return {
        "platforms": [{
            "name": "AlmaLinux-8",
            "arch_list": ["i686", "x86_64"],
            "parallel_mode_enabled": True,
        }],
        "repos": [{
            'name': 'test-repos-8',
            'type': 'rpm',
            'platform_id': 1,
        }],
        "tasks": [{
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
            "modules_yaml": (
                '---\ndocument: modulemd\nversion: 2\ndata:\n  name:'
                ' go-toolset\n  stream: "rhel8"\n  arch: x86_64\n '
                ' summary: Go\n  description: >-\n    Go Tools and'
                ' libraries\n  license:\n    module:\n    - MIT\n '
                ' dependencies:\n  - buildrequires:\n      go-toolset:'
                ' [rhel8]\n      platform: [el8]\n    requires:\n     '
                ' platform: [el8]\n  profiles:\n    common:\n      rpms:\n'
                '      - go-toolset\n  api:\n    rpms:\n    - golang\n '
                ' buildopts:\n    rpms:\n      whitelist:\n      - delve\n'
                '      - go-toolset\n      - go-toolset-1.10\n      -'
                ' go-toolset-1.10-golang\n      - go-toolset-golang\n     '
                ' - golang\n  components:\n    rpms:\n      delve:\n      '
                '  rationale: A debugger for the Go programming language\n'
                '        ref: 18f55f0e6d4d9579ac949e3a96c1c2f6e877cba8\n  '
                '      buildorder: 2\n      go-toolset:\n       '
                ' rationale: Meta package for go-toolset providing scl'
                ' enable scripts.\n        ref:'
                ' feda7855f214faf3cbb4324c74a47e4a00d117a8\n     '
                ' golang:\n        rationale: Package providing the Go'
                ' compiler toolchain.\n        ref:'
                ' 61d02fbf0e5553e82c220cfb2f403338f43496b6\n       '
                ' buildorder: 1\n...\n\n---\ndocument: modulemd\nversion:'
                ' 2\ndata:\n  name: go-toolset-devel\n  stream: "rhel8"\n '
                ' summary: Go\n  description: >-\n    Go Tools and'
                ' libraries\n  license:\n    module:\n    - MIT\n '
                ' dependencies:\n  - buildrequires:\n      go-toolset:'
                ' [rhel8]\n      platform: [el8]\n    requires:\n     '
                ' platform: [el8]\n  profiles:\n    common:\n      rpms:\n'
                '      - go-toolset\n  api:\n    rpms:\n    - golang\n '
                ' buildopts:\n    rpms:\n      whitelist:\n      - delve\n'
                '      - go-toolset\n      - go-toolset-1.10\n      -'
                ' go-toolset-1.10-golang\n      - go-toolset-golang\n     '
                ' - golang\n  components:\n    rpms:\n      delve:\n      '
                '  rationale: A debugger for the Go programming language\n'
                '        ref: 18f55f0e6d4d9579ac949e3a96c1c2f6e877cba8\n  '
                '      buildorder: 2\n      go-toolset:\n       '
                ' rationale: Meta package for go-toolset providing scl'
                ' enable scripts.\n        ref:'
                ' feda7855f214faf3cbb4324c74a47e4a00d117a8\n     '
                ' golang:\n        rationale: Package providing the Go'
                ' compiler toolchain.\n        ref:'
                ' 61d02fbf0e5553e82c220cfb2f403338f43496b6\n       '
                ' buildorder: 1\n...\n'
            ),
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
        }],
        "linked_builds": [],
        "is_secure_boot": False,
        "mock_options": {},
        "platform_flavors": [],
        "product_id": 1,
    }


@pytest.fixture
def virt_build_payload():
    return {
        "platforms": [{
            "name": "AlmaLinux-8",
            "arch_list": ["i686", "x86_64", "ppc64le"],
            "parallel_mode_enabled": True,
        }],
        "tasks": [{
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
            "modules_yaml": (
                "---\ndocument: modulemd\nversion: 2\ndata:\n  name:"
                " virt\n  stream: \"rhel\"\n  summary: Virtualization"
                " module\n  description: >-\n    A virtualization module\n"
                "  license:\n    module:\n    - MIT\n  dependencies:\n  -"
                " buildrequires:\n      platform: [el8]\n    requires:\n  "
                "    platform: [el8]\n  profiles:\n    common:\n     "
                " rpms:\n      - libguestfs\n      - libvirt-client\n     "
                " - libvirt-daemon-config-network\n      -"
                " libvirt-daemon-kvm\n  filter:\n    rpms:\n    -"
                " ocaml-hivex\n    - ocaml-hivex-debuginfo\n    -"
                " ocaml-hivex-devel\n    - ocaml-libguestfs\n    -"
                " ocaml-libguestfs-debuginfo\n    -"
                " ocaml-libguestfs-devel\n    - ocaml-libnbd\n    -"
                " ocaml-libnbd-debuginfo\n    - ocaml-libnbd-devel\n    -"
                " qemu-kvm-tests\n    - qemu-kvm-tests-debuginfo\n "
                " components:\n    rpms:\n      SLOF:\n        rationale:"
                " qemu-kvm dep\n        ref:"
                " dbd7d071c75dcc732c933f451e4b6dbc4a72b783\n       "
                " buildorder: 1\n        arches: [ppc64le]\n      hivex:\n"
                "        rationale: libguestfs dep\n        ref:"
                " 3b801940c0f8c11129805fe59590e0ee3aabb608\n       "
                " buildorder: 1\n      libguestfs:\n        rationale:"
                " Primary module content\n        ref:"
                " 61243f50c78c87d92728017318f2c1ff16d02635\n       "
                " buildorder: 4\n      libguestfs-winsupport:\n       "
                " rationale: Primary module content\n        ref:"
                " 3ea195ba2c089522b83479738a54b7e879d3eb79\n       "
                " buildorder: 5\n      libiscsi:\n        rationale:"
                " qemu-kvm dep\n        ref:"
                " 03c364210208727e90e1fa6b1fdf2cb8a5040991\n       "
                " buildorder: 1\n      libnbd:\n        rationale: Primary"
                " module content\n        ref:"
                " 951092b53e6ed1bc9eed1b29df803595d91a2c7f\n       "
                " buildorder: 1\n      libtpms:\n        rationale:"
                " Primary module content\n        ref:"
                " 86b8f6f47dc6b39d2484bb5a506f088dab36eee2\n       "
                " buildorder: 1\n      libvirt:\n        rationale:"
                " Primary module content\n        ref:"
                " 722e8085db76a4334d6eac2a4668ce0a24bb6bbd\n       "
                " buildorder: 3\n      libvirt-dbus:\n        rationale:"
                " libvirt-dbus is part of the virtualization module\n     "
                "   ref: 4a1caa1b08966a6cfcf4860c12bf61ec54cd74d3\n       "
                " buildorder: 4\n      libvirt-python:\n        rationale:"
                " Primary module content\n        ref:"
                " 062f06a46bae3b6b75fdf86cdec07eed6845f85f\n       "
                " buildorder: 4\n      nbdkit:\n        rationale: Primary"
                " module content\n        ref:"
                " 317a0878c7849f4eabe3965a83734d3f5ba8ee41\n       "
                " buildorder: 5\n      netcf:\n        rationale: libvirt"
                " dep\n        ref:"
                " 9cafbecc76f1f51c6349c46cc0765e6c6ea9997f\n       "
                " buildorder: 1\n      perl-Sys-Virt:\n        rationale:"
                " Primary module content\n        ref:"
                " 7e16e8f82d470412e6d8fe58daed83c1470d599e\n       "
                " buildorder: 4\n      qemu-kvm:\n        rationale:"
                " Primary module content\n        ref:"
                " 9cf15efa745c2df3f2968d58da9ed67b29b1300f\n       "
                " buildorder: 2\n      seabios:\n        rationale:"
                " qemu-kvm dep\n        ref:"
                " 94f4f45b8837c5e834b0ae11d368978c621c6fbc\n       "
                " buildorder: 1\n        arches: [ppc64le, x86_64]\n     "
                " sgabios:\n        rationale: qemu-kvm dep\n        ref:"
                " 643ad1528f18937fa5fa0a021a8f25dd1e252596\n       "
                " buildorder: 1\n        arches: [ppc64le, x86_64]\n     "
                " supermin:\n        rationale: libguestfs dep\n       "
                " ref: 502fabee05eb11c69d2fe29becf23e0e013a1995\n       "
                " buildorder: 2\n      swtpm:\n        rationale: Primary"
                " module content\n        ref:"
                " 12e26459a3feb201950bf8d52a9af95afd601a5b\n       "
                " buildorder: 2\n      virt-v2v:\n        rationale:"
                " Primary module content\n        ref:"
                " 22c887f059f0127d58f53e1d00b38c297e565890\n       "
                " buildorder: 6\n...\n\n---\ndocument: modulemd\nversion:"
                " 2\ndata:\n  name: virt-devel\n  stream: \"rhel\"\n "
                " summary: Virtualization module\n  description: >-\n    A"
                " virtualization module\n  license:\n    module:\n    -"
                " MIT\n  dependencies:\n  - buildrequires:\n     "
                " platform: [el8]\n    requires:\n      platform: [el8]\n "
                " profiles:\n    common:\n      rpms:\n      -"
                " libguestfs\n      - libvirt-client\n      -"
                " libvirt-daemon-config-network\n      -"
                " libvirt-daemon-kvm\n  filter:\n    rpms:\n    -"
                " ocaml-hivex\n    - ocaml-hivex-debuginfo\n    -"
                " ocaml-hivex-devel\n    - ocaml-libguestfs\n    -"
                " ocaml-libguestfs-debuginfo\n    -"
                " ocaml-libguestfs-devel\n    - ocaml-libnbd\n    -"
                " ocaml-libnbd-debuginfo\n    - ocaml-libnbd-devel\n    -"
                " qemu-kvm-tests\n    - qemu-kvm-tests-debuginfo\n "
                " components:\n    rpms:\n      SLOF:\n        rationale:"
                " qemu-kvm dep\n        ref:"
                " dbd7d071c75dcc732c933f451e4b6dbc4a72b783\n       "
                " buildorder: 1\n        arches: [ppc64le]\n      hivex:\n"
                "        rationale: libguestfs dep\n        ref:"
                " 3b801940c0f8c11129805fe59590e0ee3aabb608\n       "
                " buildorder: 1\n      libguestfs:\n        rationale:"
                " Primary module content\n        ref:"
                " 61243f50c78c87d92728017318f2c1ff16d02635\n       "
                " buildorder: 4\n      libguestfs-winsupport:\n       "
                " rationale: Primary module content\n        ref:"
                " 3ea195ba2c089522b83479738a54b7e879d3eb79\n       "
                " buildorder: 5\n      libiscsi:\n        rationale:"
                " qemu-kvm dep\n        ref:"
                " 03c364210208727e90e1fa6b1fdf2cb8a5040991\n       "
                " buildorder: 1\n      libnbd:\n        rationale: Primary"
                " module content\n        ref:"
                " 951092b53e6ed1bc9eed1b29df803595d91a2c7f\n       "
                " buildorder: 1\n      libtpms:\n        rationale:"
                " Primary module content\n        ref:"
                " 86b8f6f47dc6b39d2484bb5a506f088dab36eee2\n       "
                " buildorder: 1\n      libvirt:\n        rationale:"
                " Primary module content\n        ref:"
                " 722e8085db76a4334d6eac2a4668ce0a24bb6bbd\n       "
                " buildorder: 3\n      libvirt-dbus:\n        rationale:"
                " libvirt-dbus is part of the virtualization module\n     "
                "   ref: 4a1caa1b08966a6cfcf4860c12bf61ec54cd74d3\n       "
                " buildorder: 4\n      libvirt-python:\n        rationale:"
                " Primary module content\n        ref:"
                " 062f06a46bae3b6b75fdf86cdec07eed6845f85f\n       "
                " buildorder: 4\n      nbdkit:\n        rationale: Primary"
                " module content\n        ref:"
                " 317a0878c7849f4eabe3965a83734d3f5ba8ee41\n       "
                " buildorder: 5\n      netcf:\n        rationale: libvirt"
                " dep\n        ref:"
                " 9cafbecc76f1f51c6349c46cc0765e6c6ea9997f\n       "
                " buildorder: 1\n      perl-Sys-Virt:\n        rationale:"
                " Primary module content\n        ref:"
                " 7e16e8f82d470412e6d8fe58daed83c1470d599e\n       "
                " buildorder: 4\n      qemu-kvm:\n        rationale:"
                " Primary module content\n        ref:"
                " 9cf15efa745c2df3f2968d58da9ed67b29b1300f\n       "
                " buildorder: 2\n      seabios:\n        rationale:"
                " qemu-kvm dep\n        ref:"
                " 94f4f45b8837c5e834b0ae11d368978c621c6fbc\n       "
                " buildorder: 1\n        arches: [ppc64le, x86_64]\n     "
                " sgabios:\n        rationale: qemu-kvm dep\n        ref:"
                " 643ad1528f18937fa5fa0a021a8f25dd1e252596\n       "
                " buildorder: 1\n        arches: [ppc64le, x86_64]\n     "
                " supermin:\n        rationale: libguestfs dep\n       "
                " ref: 502fabee05eb11c69d2fe29becf23e0e013a1995\n       "
                " buildorder: 2\n      swtpm:\n        rationale: Primary"
                " module content\n        ref:"
                " 12e26459a3feb201950bf8d52a9af95afd601a5b\n       "
                " buildorder: 2\n      virt-v2v:\n        rationale:"
                " Primary module content\n        ref:"
                " 22c887f059f0127d58f53e1d00b38c297e565890\n       "
                " buildorder: 6\n...\n"
            ),
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
        }],
        "linked_builds": [],
        "is_secure_boot": False,
        "mock_options": {},
        "platform_flavors": [],
        "product_id": 1,
    }


@pytest.fixture
def ruby_build_payload():
    return {
        "platforms": [{
            "name": "AlmaLinux-8",
            "arch_list": ["i686", "x86_64", "aarch64"],
            "parallel_mode_enabled": True,
        }],
        "tasks": [{
            "refs": [
                {
                    "url": "https://git.almalinux.org/rpms/ruby.git",
                    "git_ref": "c8-stream-3.1",
                    "exist": True,
                    "enabled": True,
                    "added_artifacts": [],
                    "mock_options": {
                        "definitions": {},
                        "module_enable": ["ruby:3.1", "ruby-devel:3.1"],
                    },
                    "ref_type": 1,
                },
                {
                    "url": "https://git.almalinux.org/rpms/rubygem-pg.git",
                    "git_ref": "c8-stream-3.1",
                    "exist": True,
                    "enabled": True,
                    "added_artifacts": [],
                    "mock_options": {
                        "definitions": {},
                        "module_enable": ["ruby:3.1", "ruby-devel:3.1"],
                    },
                    "ref_type": 1,
                },
            ],
            "modules_yaml": (
                "---\ndocument: modulemd\nversion: 2\ndata:\n  name:"
                " ruby\n  stream: \"3.1\"\n  summary: An interpreter of"
                " object-oriented scripting language\n  description: >-\n "
                "   Ruby is the interpreted scripting language for quick"
                " and easy object-oriented\n    programming.  It has many"
                " features to process text files and to do system"
                " management\n    tasks (as in Perl).  It is simple,"
                " straight-forward, and extensible.\n  license:\n   "
                " module:\n    - MIT\n  dependencies:\n  -"
                " buildrequires:\n      platform: [el8]\n    requires:\n  "
                "    platform: [el8]\n  references:\n    community:"
                " http://ruby-lang.org/\n    documentation:"
                " https://www.ruby-lang.org/en/documentation/\n   "
                " tracker: https://bugs.ruby-lang.org/\n  profiles:\n   "
                " common:\n      rpms:\n      - ruby\n  api:\n    rpms:\n "
                "   - ruby\n    - ruby-bundled-gems\n    -"
                " ruby-default-gems\n    - ruby-devel\n    - ruby-libs\n  "
                "  - rubygem-abrt\n    - rubygem-bigdecimal\n    -"
                " rubygem-bundler\n    - rubygem-io-console\n    -"
                " rubygem-irb\n    - rubygem-json\n    -"
                " rubygem-minitest\n    - rubygem-mysql2\n    -"
                " rubygem-pg\n    - rubygem-power_assert\n    -"
                " rubygem-psych\n    - rubygem-rake\n    - rubygem-rdoc\n "
                "   - rubygem-test-unit\n    - rubygems\n    -"
                " rubygems-devel\n  components:\n    rpms:\n      ruby:\n "
                "       rationale: An interpreter of object-oriented"
                " scripting language\n        ref:"
                " f7bb4e8f3d0aefdb159718ac2164acdceeb2ce39\n       "
                " buildorder: 101\n        multilib: [x86_64]\n     "
                " rubygem-abrt:\n        rationale: ABRT support for"
                " Ruby\n        ref:"
                " 6f6f91e5b621808cf41fc475947950de56e71f56\n       "
                " buildorder: 102\n      rubygem-mysql2:\n       "
                " rationale: A simple, fast Mysql library for Ruby,"
                " binding to libmysql\n        ref:"
                " 7dce6c0006631d899b7b9b5836bf2aa321a24603\n       "
                " buildorder: 102\n      rubygem-pg:\n        rationale: A"
                " Ruby interface to the PostgreSQL RDBMS\n        ref:"
                " ccdbc3cfd207412b88cb787c25992b1162b1c326\n       "
                " buildorder: 102\n...\n\n---\ndocument:"
                " modulemd\nversion: 2\ndata:\n  name: ruby-devel\n "
                " stream: \"3.1\"\n  summary: An interpreter of"
                " object-oriented scripting language\n  description: >-\n "
                "   Ruby is the interpreted scripting language for quick"
                " and easy object-oriented\n    programming.  It has many"
                " features to process text files and to do system"
                " management\n    tasks (as in Perl).  It is simple,"
                " straight-forward, and extensible.\n  license:\n   "
                " module:\n    - MIT\n  dependencies:\n  -"
                " buildrequires:\n      platform: [el8]\n    requires:\n  "
                "    platform: [el8]\n  references:\n    community:"
                " http://ruby-lang.org/\n    documentation:"
                " https://www.ruby-lang.org/en/documentation/\n   "
                " tracker: https://bugs.ruby-lang.org/\n  profiles:\n   "
                " common:\n      rpms:\n      - ruby\n  api:\n    rpms:\n "
                "   - ruby\n    - ruby-bundled-gems\n    -"
                " ruby-default-gems\n    - ruby-devel\n    - ruby-libs\n  "
                "  - rubygem-abrt\n    - rubygem-bigdecimal\n    -"
                " rubygem-bundler\n    - rubygem-io-console\n    -"
                " rubygem-irb\n    - rubygem-json\n    -"
                " rubygem-minitest\n    - rubygem-mysql2\n    -"
                " rubygem-pg\n    - rubygem-power_assert\n    -"
                " rubygem-psych\n    - rubygem-rake\n    - rubygem-rdoc\n "
                "   - rubygem-test-unit\n    - rubygems\n    -"
                " rubygems-devel\n  components:\n    rpms:\n      ruby:\n "
                "       rationale: An interpreter of object-oriented"
                " scripting language\n        ref:"
                " f7bb4e8f3d0aefdb159718ac2164acdceeb2ce39\n       "
                " buildorder: 101\n        multilib: [x86_64]\n     "
                " rubygem-abrt:\n        rationale: ABRT support for"
                " Ruby\n        ref:"
                " 6f6f91e5b621808cf41fc475947950de56e71f56\n       "
                " buildorder: 102\n      rubygem-mysql2:\n       "
                " rationale: A simple, fast Mysql library for Ruby,"
                " binding to libmysql\n        ref:"
                " 7dce6c0006631d899b7b9b5836bf2aa321a24603\n       "
                " buildorder: 102\n      rubygem-pg:\n        rationale: A"
                " Ruby interface to the PostgreSQL RDBMS\n        ref:"
                " ccdbc3cfd207412b88cb787c25992b1162b1c326\n       "
                " buildorder: 102\n...\n"
            ),
            "module_name": "ruby",
            "module_stream": "3.1",
            "enabled_modules": {"buildtime": [], "runtime": []},
            "git_ref": "c8s-stream-3.1",
            "module_platform_version": "8.8",
            "selectedModules": {},
        }],
        "linked_builds": [],
        "is_secure_boot": False,
        "mock_options": {},
        "platform_flavors": [],
        "test_configuration": {},
        "product_id": 1,
    }


@pytest.fixture
def subversion_build_payload():
    return {
        "platforms": [{
            "name": "AlmaLinux-8",
            "arch_list": ["i686", "x86_64", "aarch64"],
            "parallel_mode_enabled": True,
        }],
        "tasks": [{
            "refs": [{
                "url": "https://git.almalinux.org/rpms/subversion.git",
                "git_ref": "c8-stream-1.10",
                "exist": True,
                "enabled": True,
                "added_artifacts": [],
                "mock_options": {
                    "definitions": {
                        "_without_kwallet": "1",
                        "_without_python2": "1",
                        "_with_python3": "1",
                        "_without_bdb": "1",
                        "_without_pyswig": "1",
                    },
                    "module_enable": [
                        "subversion:1.10",
                        "subversion-devel:1.10",
                        "httpd:2.4",
                        "swig:3.0",
                    ],
                },
                "ref_type": 1,
            }],
            "modules_yaml": (
                "---\ndocument: modulemd\nversion: 2\ndata:\n  name:"
                " subversion\n  stream: \"1.10\"\n  summary: Apache"
                " Subversion\n  description: >-\n    Apache Subversion, a"
                " Modern Version Control System\n  license:\n    module:\n"
                "    - MIT\n  dependencies:\n  - buildrequires:\n     "
                " httpd: [2.4]\n      platform: [el8]\n      swig: [3.0]\n"
                "    requires:\n      platform: [el8]\n  references:\n   "
                " documentation: http://subversion.apache.org/docs/\n   "
                " tracker: https://issues.apache.org/jira/projects/SVN\n "
                " profiles:\n    common:\n      rpms:\n      -"
                " subversion\n      - subversion-libs\n      -"
                " subversion-tools\n    server:\n      rpms:\n      -"
                " mod_dav_svn\n      - subversion\n      -"
                " subversion-libs\n      - subversion-tools\n  api:\n   "
                " rpms:\n    - mod_dav_svn\n    - subversion\n    -"
                " subversion-devel\n    - subversion-libs\n  filter:\n   "
                " rpms:\n    - libserf-devel\n    - python3-subversion\n  "
                "  - subversion-ruby\n    - utf8proc-devel\n  buildopts:\n"
                "    rpms:\n      macros: >\n        %_without_kwallet"
                " 1\n\n        %_without_python2 1\n\n       "
                " %_with_python3 1\n\n        %_without_bdb 1\n\n       "
                " %_without_pyswig 1\n  components:\n    rpms:\n     "
                " libserf:\n        rationale: Build dependency.\n       "
                " ref: 6ebf0093af090cf5c8d082e04ba3d028458e0f54\n       "
                " buildorder: 10\n      subversion:\n        rationale:"
                " Module API.\n        ref:"
                " a757409c2fc92983ed4ba21058e47f22941be59e\n       "
                " buildorder: 20\n      utf8proc:\n        rationale:"
                " Build dependency.\n        ref:"
                " 3a752429dbff2f4dc394a579715b23253339d776\n       "
                " buildorder: 10\n...\n\n---\ndocument: modulemd\nversion:"
                " 2\ndata:\n  name: subversion-devel\n  stream: \"1.10\"\n"
                "  summary: Apache Subversion\n  description: >-\n   "
                " Apache Subversion, a Modern Version Control System\n "
                " license:\n    module:\n    - MIT\n  dependencies:\n  -"
                " buildrequires:\n      httpd: [2.4]\n      platform:"
                " [el8]\n      swig: [3.0]\n    requires:\n      platform:"
                " [el8]\n  references:\n    documentation:"
                " http://subversion.apache.org/docs/\n    tracker:"
                " https://issues.apache.org/jira/projects/SVN\n "
                " profiles:\n    common:\n      rpms:\n      -"
                " subversion\n      - subversion-libs\n      -"
                " subversion-tools\n    server:\n      rpms:\n      -"
                " mod_dav_svn\n      - subversion\n      -"
                " subversion-libs\n      - subversion-tools\n  api:\n   "
                " rpms:\n    - mod_dav_svn\n    - subversion\n    -"
                " subversion-devel\n    - subversion-libs\n  filter:\n   "
                " rpms:\n    - libserf-devel\n    - python3-subversion\n  "
                "  - subversion-ruby\n    - utf8proc-devel\n  buildopts:\n"
                "    rpms:\n      macros: >\n        %_without_kwallet"
                " 1\n\n        %_without_python2 1\n\n       "
                " %_with_python3 1\n\n        %_without_bdb 1\n\n       "
                " %_without_pyswig 1\n  components:\n    rpms:\n     "
                " libserf:\n        rationale: Build dependency.\n       "
                " ref: 6ebf0093af090cf5c8d082e04ba3d028458e0f54\n       "
                " buildorder: 10\n      subversion:\n        rationale:"
                " Module API.\n        ref:"
                " a757409c2fc92983ed4ba21058e47f22941be59e\n       "
                " buildorder: 20\n      utf8proc:\n        rationale:"
                " Build dependency.\n        ref:"
                " 3a752429dbff2f4dc394a579715b23253339d776\n       "
                " buildorder: 10\n...\n"
            ),
            "module_name": "subversion",
            "module_stream": "1.10",
            "enabled_modules": {
                "buildtime": ["httpd:2.4", "swig:3.0"],
                "runtime": [],
            },
            "git_ref": "c8-stream-1.10",
            "module_platform_version": "8.8",
            "selectedModules": {},
        }],
        "linked_builds": [],
        "is_secure_boot": False,
        "mock_options": {},
        "platform_flavors": [],
        "product_id": 1,
    }


@pytest.fixture
def llvm_build_payload():
    return {
        "platforms": [{
            "name": "AlmaLinux-8",
            "arch_list": [
                "i686",
                "x86_64",
            ],
            "parallel_mode_enabled": True,
        }],
        "tasks": [{
            "refs": [
                {
                    "url": "https://git.almalinux.org/rpms/llvm.git",
                    "git_ref": "c8-stream-rhel8",
                    "exist": True,
                    "enabled": True,
                    "added_artifacts": [],
                    "mock_options": {
                        "definitions": {},
                        "module_enable": [
                            "llvm-toolset:rhel8",
                            "llvm-toolset-devel:rhel8",
                        ],
                    },
                    "ref_type": 1,
                },
                {
                    "url": "https://git.almalinux.org/rpms/python-lit.git",
                    "git_ref": "c8-stream-rhel8",
                    "exist": True,
                    "enabled": True,
                    "added_artifacts": [],
                    "mock_options": {
                        "definitions": {},
                        "module_enable": [
                            "llvm-toolset:rhel8",
                            "llvm-toolset-devel:rhel8",
                        ],
                    },
                    "ref_type": 1,
                },
                {
                    "url": ("https://git.almalinux.org/rpms/compiler-rt.git"),
                    "git_ref": "c8-stream-rhel8",
                    "exist": True,
                    "enabled": False,
                    "added_artifacts": [
                        "compiler-rt-0:13.0.1-1.module+el8.6.0+14118+d530a951.i686",
                        "compiler-rt-0:13.0.1-1.module+el8.6.0+14118+d530a951.src",
                        "compiler-rt-0:13.0.1-1.module+el8.6.0+14118+d530a951.x86_64",
                    ],
                    "mock_options": {
                        "definitions": {},
                        "module_enable": [
                            "llvm-toolset:rhel8",
                            "llvm-toolset-devel:rhel8",
                        ],
                    },
                    "ref_type": 1,
                },
                {
                    "url": "https://git.almalinux.org/rpms/clang.git",
                    "git_ref": "c8-stream-rhel8",
                    "exist": True,
                    "enabled": False,
                    "added_artifacts": [
                        "clang-0:13.0.1-1.module+el8.6.0+14118+d530a951.i686",
                        "clang-0:13.0.1-1.module+el8.6.0+14118+d530a951.src",
                        "clang-0:13.0.1-1.module+el8.6.0+14118+d530a951.x86_64",
                    ],
                    "mock_options": {
                        "definitions": {},
                        "module_enable": [
                            "llvm-toolset:rhel8",
                            "llvm-toolset-devel:rhel8",
                        ],
                    },
                    "ref_type": 1,
                },
            ],
            "modules_yaml": (
                "---\ndocument: modulemd\nversion: 2\ndata:\n  name:"
                " llvm-toolset\n  stream: \"rhel8\"\n  summary: LLVM\n "
                " description: >-\n    LLVM Tools and libraries\n "
                " license:\n    module:\n    - MIT\n  dependencies:\n  -"
                " buildrequires:\n      platform: [el8]\n    requires:\n  "
                "    platform: [el8]\n  profiles:\n    common:\n     "
                " rpms:\n      - llvm-toolset\n  api:\n    rpms:\n    -"
                " clang\n    - clang-analyzer\n    - clang-devel\n    -"
                " clang-libs\n    - clang-tools-extra\n    -"
                " git-clang-format\n    - lld\n    - lld-libs\n    -"
                " lldb\n    - lldb-devel\n    - llvm\n    - llvm-devel\n  "
                "  - llvm-libs\n  components:\n    rpms:\n      clang:\n  "
                "      rationale: clang tools and libraries\n        ref:"
                " 5cab2f5c202ed9f3f37bfa89ccd1d009340697f8\n       "
                " buildorder: 1\n        multilib: [x86_64]\n     "
                " compiler-rt:\n        rationale: LLVM compiler intrinsic"
                " and sanitizer libraries\n        ref:"
                " e078d98d28afceca1e7b1ca30c8926afabe520e0\n       "
                " buildorder: 1\n        multilib: [x86_64]\n     "
                " libomp:\n        rationale: LLVM OpenMP runtime\n       "
                " ref: 745d59987920ce8491daf7a32dac96705f76303f\n       "
                " buildorder: 2\n        multilib: [x86_64]\n      lld:\n "
                "       rationale: LLVM linker\n        ref:"
                " 4f810a0149c260b27df0568a115a8875f9fa1b2f\n       "
                " buildorder: 1\n        multilib: [x86_64]\n      lldb:\n"
                "        rationale: lldb debugger\n        ref:"
                " 47eead6e7a852635ba3a4017910abc2c3f716445\n       "
                " buildorder: 2\n        multilib: [x86_64]\n      llvm:\n"
                "        rationale: LLVM tools and libraries\n        ref:"
                " c143e4f101a5cc14014ea3b5bceeb13fe697bb5a\n       "
                " multilib: [x86_64]\n      python-lit:\n       "
                " rationale: Lit test runner for LLVM\n        ref:"
                " 861093e065602d0e1cb1e220d160af14565ac8e6\n...\n\n---\ndocument:"
                " modulemd\nversion: 2\ndata:\n  name:"
                " llvm-toolset-devel\n  stream: \"rhel8\"\n  summary:"
                " LLVM\n  description: >-\n    LLVM Tools and libraries\n "
                " license:\n    module:\n    - MIT\n  dependencies:\n  -"
                " buildrequires:\n      platform: [el8]\n    requires:\n  "
                "    platform: [el8]\n  profiles:\n    common:\n     "
                " rpms:\n      - llvm-toolset\n  api:\n    rpms:\n    -"
                " clang\n    - clang-analyzer\n    - clang-devel\n    -"
                " clang-libs\n    - clang-tools-extra\n    -"
                " git-clang-format\n    - lld\n    - lld-libs\n    -"
                " lldb\n    - lldb-devel\n    - llvm\n    - llvm-devel\n  "
                "  - llvm-libs\n  components:\n    rpms:\n      clang:\n  "
                "      rationale: clang tools and libraries\n        ref:"
                " 5cab2f5c202ed9f3f37bfa89ccd1d009340697f8\n       "
                " buildorder: 1\n        multilib: [x86_64]\n     "
                " compiler-rt:\n        rationale: LLVM compiler intrinsic"
                " and sanitizer libraries\n        ref:"
                " e078d98d28afceca1e7b1ca30c8926afabe520e0\n       "
                " buildorder: 1\n        multilib: [x86_64]\n     "
                " libomp:\n        rationale: LLVM OpenMP runtime\n       "
                " ref: 745d59987920ce8491daf7a32dac96705f76303f\n       "
                " buildorder: 2\n        multilib: [x86_64]\n      lld:\n "
                "       rationale: LLVM linker\n        ref:"
                " 4f810a0149c260b27df0568a115a8875f9fa1b2f\n       "
                " buildorder: 1\n        multilib: [x86_64]\n      lldb:\n"
                "        rationale: lldb debugger\n        ref:"
                " 47eead6e7a852635ba3a4017910abc2c3f716445\n       "
                " buildorder: 2\n        multilib: [x86_64]\n      llvm:\n"
                "        rationale: LLVM tools and libraries\n        ref:"
                " c143e4f101a5cc14014ea3b5bceeb13fe697bb5a\n       "
                " multilib: [x86_64]\n      python-lit:\n       "
                " rationale: Lit test runner for LLVM\n        ref:"
                " 861093e065602d0e1cb1e220d160af14565ac8e6\n...\n"
            ),
            "module_name": "llvm-toolset",
            "module_stream": "rhel8",
            "enabled_modules": {"buildtime": [], "runtime": []},
            "git_ref": "c8s-stream-rhel8",
            "module_platform_version": "8.6",
            "selectedModules": {},
        }],
        "linked_builds": [],
        "is_secure_boot": False,
        "mock_options": {},
        "platform_flavors": [],
        "product_id": 1,
    }


@pytest.fixture
def build_payload() -> typing.Dict[str, typing.Any]:
    return {
        "platforms": [{
            "name": "AlmaLinux-8",
            "arch_list": ["i686", "x86_64"],
            "parallel_mode_enabled": True,
        }],
        "tasks": [{
            "git_ref": "c8",
            "url": "https://git.almalinux.org/rpms/chan.git",
            "ref_type": 4,
            "mock_options": {},
        }],
        "linked_builds": [],
        "is_secure_boot": False,
        "mock_options": {},
        "platform_flavors": [],
        "product_id": 1,
    }


@pytest.fixture
async def modular_build(
    async_session: AsyncSession,
    modular_build_payload: dict,
) -> typing.AsyncIterable[Build]:
    build = await create_build(
        async_session,
        BuildCreate(**modular_build_payload),
        user_id=ADMIN_USER_ID,
    )
    await async_session.commit()
    yield build


@pytest.fixture
async def virt_modular_build(
    async_session: AsyncSession,
    virt_build_payload: dict,
) -> typing.AsyncIterable:
    build = await create_build(
        async_session,
        BuildCreate(**virt_build_payload),
        user_id=ADMIN_USER_ID,
    )
    await async_session.commit()
    yield build


@pytest.fixture
async def ruby_modular_build(
    async_session: AsyncSession,
    ruby_build_payload: dict,
) -> typing.AsyncIterable:
    build = await create_build(
        async_session,
        BuildCreate(**ruby_build_payload),
        user_id=ADMIN_USER_ID,
    )
    await async_session.commit()
    yield build


@pytest.fixture
async def subversion_modular_build(
    async_session: AsyncSession,
    subversion_build_payload: dict,
) -> typing.AsyncIterable:
    build = await create_build(
        async_session,
        BuildCreate(**subversion_build_payload),
        user_id=ADMIN_USER_ID,
    )
    await async_session.commit()
    yield build


@pytest.fixture
async def llvm_modular_build(
    async_session: AsyncSession,
    llvm_build_payload: dict,
) -> typing.AsyncIterable:
    build = await create_build(
        async_session,
        BuildCreate(**llvm_build_payload),
        user_id=ADMIN_USER_ID,
    )
    await async_session.commit()
    yield build


@pytest.fixture
async def regular_build(
    base_platform,
    base_product,
    async_session: AsyncSession,
    build_payload: dict,
) -> typing.AsyncIterable[Build]:
    build = await create_build(
        async_session,
        BuildCreate(**build_payload),
        user_id=ADMIN_USER_ID,
    )
    await async_session.commit()
    yield build


@pytest.fixture
async def regular_build_with_user_product(
    async_session: AsyncSession,
    build_payload: dict,
    create_build_rpm_repo,
    create_log_repo,
    modify_repository,
) -> typing.AsyncIterable[Build]:
    payload = copy.deepcopy(build_payload)
    user_product_id = (
        (
            await async_session.execute(
                select(Product.id).where(Product.is_community.is_(True))
            )
        )
        .scalars()
        .first()
    )
    payload['product_id'] = user_product_id
    build = await create_build(
        async_session,
        BuildCreate(**payload),
        user_id=ADMIN_USER_ID,
    )
    await async_session.commit()
    await _start_build(build.id, BuildCreate(**payload))
    yield await get_builds(async_session, build_id=build.id)


@pytest.fixture
def get_rpm_packages_info(monkeypatch):
    def func(artifacts):
        return {
            artifact.href: get_rpm_pkg_info(artifact) for artifact in artifacts
        }

    monkeypatch.setattr("alws.crud.build_node.get_rpm_packages_info", func)


@pytest.fixture
def get_packages_info_from_pulp(monkeypatch):
    async def func(arg, arg2):
        return

    monkeypatch.setattr(
        "alws.utils.multilib.MultilibProcessor.add_multilib_packages", func
    )


@pytest.fixture
async def build_for_release(
    async_session: AsyncSession,
    regular_build: Build,
) -> typing.AsyncIterable[Build]:
    yield await get_builds(async_session, build_id=regular_build.id)


@pytest.fixture
async def modular_build_for_release(
    async_session: AsyncSession,
    modular_build: Build,
) -> typing.AsyncIterable[Build]:
    yield await get_builds(async_session, build_id=modular_build.id)

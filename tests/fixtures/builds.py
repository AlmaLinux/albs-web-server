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
def virt_build_payload() -> typing.Dict[str, typing.Any]:
    return {
        "platforms": [
            {
                "name": "AlmaLinux-8",
                "arch_list": [
                    "x86_64"
                ],
                "parallel_mode_enabled": True
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
                            "module_enable": [
                                "virt:rhel",
                                "virt-devel:rhel"
                            ]
                        },
                        "ref_type": 1
                    },
                    {
                        "url": "https://git.almalinux.org/rpms/hivex.git",
                        "git_ref": "c8-stream-rhel",
                        "exist": True,
                        "enabled": True,
                        "added_artifacts": [],
                        "mock_options": {
                            "definitions": {},
                            "module_enable": [
                                "virt:rhel",
                                "virt-devel:rhel"
                            ]
                        },
                        "ref_type": 1
                    },
                    {
                        "url": "https://git.almalinux.org/rpms/libiscsi.git",
                        "git_ref": "c8-stream-rhel",
                        "exist": True,
                        "enabled": True,
                        "added_artifacts": [],
                        "mock_options": {
                            "definitions": {},
                            "module_enable": [
                                "virt:rhel",
                                "virt-devel:rhel"
                            ]
                        },
                        "ref_type": 1
                    },
                    {
                        "url": "https://git.almalinux.org/rpms/libnbd.git",
                        "git_ref": "c8-stream-rhel",
                        "exist": True,
                        "enabled": True,
                        "added_artifacts": [],
                        "mock_options": {
                            "definitions": {},
                            "module_enable": [
                                "virt:rhel",
                                "virt-devel:rhel"
                            ]
                        },
                        "ref_type": 1
                    },
                    {
                        "url": "https://git.almalinux.org/rpms/netcf.git",
                        "git_ref": "c8-stream-rhel",
                        "exist": True,
                        "enabled": True,
                        "added_artifacts": [],
                        "mock_options": {
                            "definitions": {},
                            "module_enable": [
                                "virt:rhel",
                                "virt-devel:rhel"
                            ]
                        },
                        "ref_type": 1
                    },
                    {
                        "url": "https://git.almalinux.org/rpms/seabios.git",
                        "git_ref": "c8-stream-rhel",
                        "exist": True,
                        "enabled": True,
                        "added_artifacts": [],
                        "mock_options": {
                            "definitions": {},
                            "module_enable": [
                                "virt:rhel",
                                "virt-devel:rhel"
                            ]
                        },
                        "ref_type": 1
                    },
                    {
                        "url": "https://git.almalinux.org/rpms/sgabios.git",
                        "git_ref": "c8-stream-rhel",
                        "exist": True,
                        "enabled": True,
                        "added_artifacts": [],
                        "mock_options": {
                            "definitions": {},
                            "module_enable": [
                                "virt:rhel",
                                "virt-devel:rhel"
                            ]
                        },
                        "ref_type": 1
                    },
                    {
                        "url": "https://git.almalinux.org/rpms/qemu-kvm.git",
                        "git_ref": "c8-stream-rhel",
                        "exist": True,
                        "enabled": True,
                        "added_artifacts": [],
                        "mock_options": {
                            "definitions": {},
                            "module_enable": [
                                "virt:rhel",
                                "virt-devel:rhel"
                            ]
                        },
                        "ref_type": 1
                    },
                    {
                        "url": "https://git.almalinux.org/rpms/supermin.git",
                        "git_ref": "c8-stream-rhel",
                        "exist": True,
                        "enabled": True,
                        "added_artifacts": [],
                        "mock_options": {
                            "definitions": {},
                            "module_enable": [
                                "virt:rhel",
                                "virt-devel:rhel"
                            ]
                        },
                        "ref_type": 1
                    },
                    {
                        "url": "https://git.almalinux.org/rpms/libvirt.git",
                        "git_ref": "c8-stream-rhel",
                        "exist": True,
                        "enabled": True,
                        "added_artifacts": [],
                        "mock_options": {
                            "definitions": {},
                            "module_enable": [
                                "virt:rhel",
                                "virt-devel:rhel"
                            ]
                        },
                        "ref_type": 1
                    },
                    {
                        "url": "https://git.almalinux.org/rpms/libguestfs.git",
                        "git_ref": "a8-stream-rhel",
                        "exist": True,
                        "enabled": True,
                        "added_artifacts": [],
                        "mock_options": {
                            "definitions": {},
                            "module_enable": [
                                "virt:rhel",
                                "virt-devel:rhel"
                            ]
                        },
                        "ref_type": 1
                    },
                    {
                        "url": "https://git.almalinux.org/rpms/libvirt-dbus.git",
                        "git_ref": "c8-stream-rhel",
                        "exist": True,
                        "enabled": True,
                        "added_artifacts": [],
                        "mock_options": {
                            "definitions": {},
                            "module_enable": [
                                "virt:rhel",
                                "virt-devel:rhel"
                            ]
                        },
                        "ref_type": 1
                    },
                    {
                        "url": "https://git.almalinux.org/rpms/libvirt-python.git",
                        "git_ref": "c8-stream-rhel",
                        "exist": True,
                        "enabled": True,
                        "added_artifacts": [],
                        "mock_options": {
                            "definitions": {},
                            "module_enable": [
                                "virt:rhel",
                                "virt-devel:rhel"
                            ]
                        },
                        "ref_type": 1
                    },
                    {
                        "url": "https://git.almalinux.org/rpms/perl-Sys-Virt.git",
                        "git_ref": "c8-stream-rhel",
                        "exist": True,
                        "enabled": True,
                        "added_artifacts": [],
                        "mock_options": {
                            "definitions": {},
                            "module_enable": [
                                "virt:rhel",
                                "virt-devel:rhel"
                            ]
                        },
                        "ref_type": 1
                    },
                    {
                        "url": "https://git.almalinux.org/rpms/libguestfs-winsupport.git",
                        "git_ref": "c8-stream-rhel",
                        "exist": True,
                        "enabled": True,
                        "added_artifacts": [],
                        "mock_options": {
                            "definitions": {},
                            "module_enable": [
                                "virt:rhel",
                                "virt-devel:rhel"
                            ]
                        },
                        "ref_type": 1
                    },
                    {
                        "url": "https://git.almalinux.org/rpms/nbdkit.git",
                        "git_ref": "c8-stream-rhel",
                        "exist": True,
                        "enabled": True,
                        "added_artifacts": [],
                        "mock_options": {
                            "definitions": {},
                            "module_enable": [
                                "virt:rhel",
                                "virt-devel:rhel"
                            ]
                        },
                        "ref_type": 1
                    },
                    {
                        "url": "https://git.almalinux.org/rpms/virt-v2v.git",
                        "git_ref": "c8-stream-rhel",
                        "exist": True,
                        "enabled": True,
                        "added_artifacts": [],
                        "mock_options": {
                            "definitions": {},
                            "module_enable": [
                                "virt:rhel",
                                "virt-devel:rhel"
                            ]
                        },
                        "ref_type": 1
                    }
                ],
                "modules_yaml": "---\ndocument: modulemd\nversion: 2\ndata:\n  name: virt\n  stream: \"rhel\"\n  summary: Virtualization module\n  description: >-\n    A virtualization module\n  license:\n    module:\n    - MIT\n  dependencies:\n  - buildrequires:\n      platform: [el8]\n    requires:\n      platform: [el8]\n  profiles:\n    common:\n      rpms:\n      - libguestfs\n      - libvirt-client\n      - libvirt-daemon-config-network\n      - libvirt-daemon-kvm\n  filter:\n    rpms:\n    - ocaml-hivex\n    - ocaml-hivex-debuginfo\n    - ocaml-hivex-devel\n    - ocaml-libguestfs\n    - ocaml-libguestfs-debuginfo\n    - ocaml-libguestfs-devel\n    - ocaml-libnbd\n    - ocaml-libnbd-debuginfo\n    - ocaml-libnbd-devel\n    - qemu-kvm-tests\n    - qemu-kvm-tests-debuginfo\n  components:\n    rpms:\n      SLOF:\n        rationale: qemu-kvm dep\n        ref: f80e03853d9036a595fcd08bc2dd044399f64c48\n        buildorder: 1\n        arches: [ppc64le]\n      hivex:\n        rationale: libguestfs dep\n        ref: 09b2ee4848da1e9a15eec08c15c9c9a12b78c98d\n        buildorder: 1\n      libguestfs:\n        rationale: Primary module content\n        ref: f2ffb5b703d156a1d45d1e12b9e87d77d811f6e3\n        buildorder: 4\n      libguestfs-winsupport:\n        rationale: Primary module content\n        ref: a0beee3b26e0326acb73f3536d3268fb5fbe4913\n        buildorder: 5\n      libiscsi:\n        rationale: qemu-kvm dep\n        ref: 83a43a62732b85ae2154c321b61f146d17a661ce\n        buildorder: 1\n      libnbd:\n        rationale: Primary module content\n        ref: f7804f3d1a320d383d044b0ec300c91ba70ae078\n        buildorder: 1\n      libtpms:\n        rationale: Primary module content\n        ref: 8b666e5a86876709dfec37ea39d4d85484badda5\n        buildorder: 1\n      libvirt:\n        rationale: Primary module content\n        ref: deba22431021b23eade365e9f554704f37a26241\n        buildorder: 3\n      libvirt-dbus:\n        rationale: libvirt-dbus is part of the virtualization module\n        ref: a79a52502277a9da55b6fc4b31e510f4f57373a3\n        buildorder: 4\n      libvirt-python:\n        rationale: Primary module content\n        ref: 2b369bdd6ed5986c0d67cc98c37452744ed8b76c\n        buildorder: 4\n      nbdkit:\n        rationale: Primary module content\n        ref: e6e531fd5c4fb9fc3ecbae3cc83feb2a0783f5a1\n        buildorder: 5\n      netcf:\n        rationale: libvirt dep\n        ref: 479db06901613a830522072b6c6002525d0cf8f5\n        buildorder: 1\n      perl-Sys-Virt:\n        rationale: Primary module content\n        ref: 2bf1f82db2c3919451ca87bbafe4bb4a77dcf403\n        buildorder: 4\n      qemu-kvm:\n        rationale: Primary module content\n        ref: cb066cbf0338786b8398e7a8b504504fb2be28ec\n        buildorder: 2\n      seabios:\n        rationale: qemu-kvm dep\n        ref: 6ce4fe9c6560521d7997eac00a8c90686b86eaa5\n        buildorder: 1\n        arches: [ppc64le, x86_64]\n      sgabios:\n        rationale: qemu-kvm dep\n        ref: 31f24e6cba356099158a0697c8dd7f0bf6bd4a61\n        buildorder: 1\n        arches: [ppc64le, x86_64]\n      supermin:\n        rationale: libguestfs dep\n        ref: 25c779ec1660f1bddc329ee34c3e85c7f0a89544\n        buildorder: 2\n      swtpm:\n        rationale: Primary module content\n        ref: ac7ae47c19e454e57033b9f7bb0ffb92de6650ed\n        buildorder: 2\n      virt-v2v:\n        rationale: Primary module content\n        ref: 4309fddf67271b08724d9e90170b3f4b9f7ac68d\n        buildorder: 6\n...\n\n---\ndocument: modulemd\nversion: 2\ndata:\n  name: virt-devel\n  stream: \"rhel\"\n  summary: Virtualization module\n  description: >-\n    A virtualization module\n  license:\n    module:\n    - MIT\n  dependencies:\n  - buildrequires:\n      platform: [el8]\n    requires:\n      platform: [el8]\n  profiles:\n    common:\n      rpms:\n      - libguestfs\n      - libvirt-client\n      - libvirt-daemon-config-network\n      - libvirt-daemon-kvm\n  filter:\n    rpms:\n    - ocaml-hivex\n    - ocaml-hivex-debuginfo\n    - ocaml-hivex-devel\n    - ocaml-libguestfs\n    - ocaml-libguestfs-debuginfo\n    - ocaml-libguestfs-devel\n    - ocaml-libnbd\n    - ocaml-libnbd-debuginfo\n    - ocaml-libnbd-devel\n    - qemu-kvm-tests\n    - qemu-kvm-tests-debuginfo\n  components:\n    rpms:\n      SLOF:\n        rationale: qemu-kvm dep\n        ref: f80e03853d9036a595fcd08bc2dd044399f64c48\n        buildorder: 1\n        arches: [ppc64le]\n      hivex:\n        rationale: libguestfs dep\n        ref: 09b2ee4848da1e9a15eec08c15c9c9a12b78c98d\n        buildorder: 1\n      libguestfs:\n        rationale: Primary module content\n        ref: f2ffb5b703d156a1d45d1e12b9e87d77d811f6e3\n        buildorder: 4\n      libguestfs-winsupport:\n        rationale: Primary module content\n        ref: a0beee3b26e0326acb73f3536d3268fb5fbe4913\n        buildorder: 5\n      libiscsi:\n        rationale: qemu-kvm dep\n        ref: 83a43a62732b85ae2154c321b61f146d17a661ce\n        buildorder: 1\n      libnbd:\n        rationale: Primary module content\n        ref: f7804f3d1a320d383d044b0ec300c91ba70ae078\n        buildorder: 1\n      libtpms:\n        rationale: Primary module content\n        ref: 8b666e5a86876709dfec37ea39d4d85484badda5\n        buildorder: 1\n      libvirt:\n        rationale: Primary module content\n        ref: deba22431021b23eade365e9f554704f37a26241\n        buildorder: 3\n      libvirt-dbus:\n        rationale: libvirt-dbus is part of the virtualization module\n        ref: a79a52502277a9da55b6fc4b31e510f4f57373a3\n        buildorder: 4\n      libvirt-python:\n        rationale: Primary module content\n        ref: 2b369bdd6ed5986c0d67cc98c37452744ed8b76c\n        buildorder: 4\n      nbdkit:\n        rationale: Primary module content\n        ref: e6e531fd5c4fb9fc3ecbae3cc83feb2a0783f5a1\n        buildorder: 5\n      netcf:\n        rationale: libvirt dep\n        ref: 479db06901613a830522072b6c6002525d0cf8f5\n        buildorder: 1\n      perl-Sys-Virt:\n        rationale: Primary module content\n        ref: 2bf1f82db2c3919451ca87bbafe4bb4a77dcf403\n        buildorder: 4\n      qemu-kvm:\n        rationale: Primary module content\n        ref: cb066cbf0338786b8398e7a8b504504fb2be28ec\n        buildorder: 2\n      seabios:\n        rationale: qemu-kvm dep\n        ref: 6ce4fe9c6560521d7997eac00a8c90686b86eaa5\n        buildorder: 1\n        arches: [ppc64le, x86_64]\n      sgabios:\n        rationale: qemu-kvm dep\n        ref: 31f24e6cba356099158a0697c8dd7f0bf6bd4a61\n        buildorder: 1\n        arches: [ppc64le, x86_64]\n      supermin:\n        rationale: libguestfs dep\n        ref: 25c779ec1660f1bddc329ee34c3e85c7f0a89544\n        buildorder: 2\n      swtpm:\n        rationale: Primary module content\n        ref: ac7ae47c19e454e57033b9f7bb0ffb92de6650ed\n        buildorder: 2\n      virt-v2v:\n        rationale: Primary module content\n        ref: 4309fddf67271b08724d9e90170b3f4b9f7ac68d\n        buildorder: 6\n...\n",
                "module_name": "virt",
                "module_stream": "rhel",
                "enabled_modules": {
                    "buildtime": [],
                    "runtime": []
                },
                "git_ref": "c8-stream-rhel",
                "module_platform_version": "8.6",
                "selectedModules": {}
            }
        ],
        "linked_builds": [],
        "is_secure_boot": False,
        "mock_options": {},
        "platform_flavors": [],
        "product_id": 1
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
async def virt_build(
    session: AsyncSession,
    virt_build_payload: dict,
) -> typing.AsyncIterable[Build]:
    yield await create_build(
        session,
        BuildCreate(**virt_build_payload),
        user_id=ADMIN_USER_ID,
    )


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
    #monkeypatch.setattr("alws.utils.multilib.get_rpm_package_info", func)


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

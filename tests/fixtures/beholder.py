import copy

import pytest

from alws.models import BuildTaskArtifact
from alws.pulp_models import RpmPackage
from alws.utils.beholder_client import BeholderClient
from alws.utils.multilib import MultilibProcessor
from alws.utils.parsing import parse_rpm_nevra


@pytest.fixture
def enable_beholder(monkeypatch):
    monkeypatch.setattr(
        'alws.crud.build_node.settings.package_beholder_enabled',
        True,
    )


@pytest.fixture
def beholder_virt_response():
    return {
        "arch": "x86_64",
        "artifacts": [
            {
                "packages": [
                    {
                        "arch": "src",
                        "epoch": 0,
                        "name": "hivex",
                        "release": "23.module_el8.6.0+2880+7d9e3703",
                        "repositories": [
                            {"arch": "src", "name": "almalinux-8-appstream"}
                        ],
                        "version": "1.3.18",
                    },
                    {
                        "arch": "x86_64",
                        "epoch": 0,
                        "name": "hivex",
                        "release": "23.module_el8.6.0+2880+7d9e3703",
                        "repositories": [
                            {"arch": "x86_64", "name": "almalinux-8-appstream"}
                        ],
                        "version": "1.3.18",
                    },
                    {
                        "arch": "x86_64",
                        "epoch": 0,
                        "name": "hivex-debuginfo",
                        "release": "23.module_el8.6.0+2880+7d9e3703",
                        "repositories": [
                            {
                                "arch": "x86_64",
                                "name": "almalinux-8-appstream-debuginfo",
                            }
                        ],
                        "version": "1.3.18",
                    },
                    {
                        "arch": "x86_64",
                        "epoch": 0,
                        "name": "hivex-debugsource",
                        "release": "23.module_el8.6.0+2880+7d9e3703",
                        "repositories": [
                            {
                                "arch": "x86_64",
                                "name": "almalinux-8-appstream-debuginfo",
                            }
                        ],
                        "version": "1.3.18",
                    },
                    {
                        "arch": "x86_64",
                        "epoch": 0,
                        "name": "hivex-devel",
                        "release": "23.module_el8.6.0+2880+7d9e3703",
                        "repositories": [
                            {"arch": "x86_64", "name": "almalinux-8-appstream"}
                        ],
                        "version": "1.3.18",
                    },
                ],
                "sourcerpm": {
                    "epoch": 0,
                    "name": "hivex",
                    "release": "23.module_el8.6.0+2880+7d9e3703",
                    "version": "1.3.18",
                },
            },
            {
                "packages": [
                    {
                        "arch": "src",
                        "epoch": 15,
                        "name": "qemu-kvm",
                        "release": "32.module_el8.8.0+3553+bd08596b",
                        "repositories": [
                            {"arch": "src", "name": "almalinux-8-appstream"}
                        ],
                        "version": "6.2.0",
                    },
                    {
                        "arch": "x86_64",
                        "epoch": 15,
                        "name": "qemu-kvm",
                        "release": "32.module_el8.8.0+3553+bd08596b",
                        "repositories": [
                            {"arch": "x86_64", "name": "almalinux-8-appstream"}
                        ],
                        "version": "6.2.0",
                    },
                    {
                        "arch": "x86_64",
                        "epoch": 15,
                        "name": "qemu-kvm-debuginfo",
                        "release": "32.module_el8.8.0+3553+bd08596b",
                        "repositories": [
                            {
                                "arch": "x86_64",
                                "name": "almalinux-8-appstream-debuginfo",
                            }
                        ],
                        "version": "6.2.0",
                    },
                    {
                        "arch": "x86_64",
                        "epoch": 15,
                        "name": "qemu-kvm-debugsource",
                        "release": "32.module_el8.8.0+3553+bd08596b",
                        "repositories": [
                            {
                                "arch": "x86_64",
                                "name": "almalinux-8-appstream-debuginfo",
                            }
                        ],
                        "version": "6.2.0",
                    },
                ],
                "sourcerpm": {
                    "epoch": 15,
                    "name": "qemu-kvm",
                    "release": "32.module_el8.8.0+3553+bd08596b",
                    "version": "6.2.0",
                },
            },
        ],
        "components": [
            {
                "arches": ["aarch64", "i686", "ppc64le", "s390x", "x86_64"],
                "buildorder": 1,
                "name": "SLOF",
                "ref": "dbd7d071c75dcc732c933f451e4b6dbc4a72b783",
            },
            {
                "arches": ["aarch64", "i686", "ppc64le", "s390x", "x86_64"],
                "buildorder": 1,
                "name": "hivex",
                "ref": "3b801940c0f8c11129805fe59590e0ee3aabb608",
            },
            {
                "arches": ["aarch64", "i686", "ppc64le", "s390x", "x86_64"],
                "buildorder": 2,
                "name": "qemu-kvm",
                "ref": "9cf15efa745c2df3f2968d58da9ed67b29b1300f",
            },
        ],
        "context": "9edba152",
        "distribution": {"name": "AlmaLinux", "version": "8"},
        "name": "virt",
        "repository": {"arch": "x86_64", "name": "almalinux-8-appstream"},
        "stream": "rhel",
        "type": "module",
        "version": 8080020230712134837,
    }


@pytest.fixture
def beholder_virt_devel_response():
    return {
        "arch": "x86_64",
        "artifacts": [
            {
                "packages": [
                    {
                        "arch": "i686",
                        "epoch": 0,
                        "name": "hivex",
                        "release": "23.module_el8.6.0+2880+7d9e3703",
                        "repositories": [
                            {
                                "arch": "x86_64",
                                "name": "almalinux-8-powertools",
                            }
                        ],
                        "version": "1.3.18",
                    },
                    {
                        "arch": "i686",
                        "epoch": 0,
                        "name": "hivex-debuginfo",
                        "release": "23.module_el8.6.0+2880+7d9e3703",
                        "repositories": [
                            {
                                "arch": "x86_64",
                                "name": "almalinux-8-powertools-debuginfo",
                            }
                        ],
                        "version": "1.3.18",
                    },
                    {
                        "arch": "i686",
                        "epoch": 0,
                        "name": "hivex-debugsource",
                        "release": "23.module_el8.6.0+2880+7d9e3703",
                        "repositories": [
                            {
                                "arch": "x86_64",
                                "name": "almalinux-8-powertools-debuginfo",
                            }
                        ],
                        "version": "1.3.18",
                    },
                    {
                        "arch": "i686",
                        "epoch": 0,
                        "name": "hivex-devel",
                        "release": "23.module_el8.6.0+2880+7d9e3703",
                        "repositories": [
                            {
                                "arch": "x86_64",
                                "name": "almalinux-8-powertools",
                            }
                        ],
                        "version": "1.3.18",
                    },
                    {
                        "arch": "i686",
                        "epoch": 0,
                        "name": "ocaml-hivex",
                        "release": "23.module_el8.6.0+2880+7d9e3703",
                        "repositories": [
                            {
                                "arch": "x86_64",
                                "name": "almalinux-8-powertools",
                            }
                        ],
                        "version": "1.3.18",
                    },
                    {
                        "arch": "x86_64",
                        "epoch": 0,
                        "name": "ocaml-hivex",
                        "release": "23.module_el8.6.0+2880+7d9e3703",
                        "repositories": [
                            {
                                "arch": "x86_64",
                                "name": "almalinux-8-powertools",
                            }
                        ],
                        "version": "1.3.18",
                    },
                    {
                        "arch": "i686",
                        "epoch": 0,
                        "name": "ocaml-hivex-debuginfo",
                        "release": "23.module_el8.6.0+2880+7d9e3703",
                        "repositories": [
                            {
                                "arch": "x86_64",
                                "name": "almalinux-8-powertools-debuginfo",
                            }
                        ],
                        "version": "1.3.18",
                    },
                    {
                        "arch": "x86_64",
                        "epoch": 0,
                        "name": "ocaml-hivex-debuginfo",
                        "release": "23.module_el8.6.0+2880+7d9e3703",
                        "repositories": [
                            {
                                "arch": "x86_64",
                                "name": "almalinux-8-powertools-debuginfo",
                            }
                        ],
                        "version": "1.3.18",
                    },
                    {
                        "arch": "i686",
                        "epoch": 0,
                        "name": "ocaml-hivex-devel",
                        "release": "23.module_el8.6.0+2880+7d9e3703",
                        "repositories": [
                            {
                                "arch": "x86_64",
                                "name": "almalinux-8-powertools",
                            }
                        ],
                        "version": "1.3.18",
                    },
                    {
                        "arch": "x86_64",
                        "epoch": 0,
                        "name": "ocaml-hivex-devel",
                        "release": "23.module_el8.6.0+2880+7d9e3703",
                        "repositories": [
                            {
                                "arch": "x86_64",
                                "name": "almalinux-8-powertools",
                            }
                        ],
                        "version": "1.3.18",
                    },
                ],
                "sourcerpm": {
                    "epoch": 0,
                    "name": "hivex",
                    "release": "23.module_el8.6.0+2880+7d9e3703",
                    "version": "1.3.18",
                },
            },
        ],
        "components": [
            {
                "arches": ["aarch64", "i686", "ppc64le", "s390x", "x86_64"],
                "buildorder": 1,
                "name": "SLOF",
                "ref": "dbd7d071c75dcc732c933f451e4b6dbc4a72b783",
            },
            {
                "arches": ["aarch64", "i686", "ppc64le", "s390x", "x86_64"],
                "buildorder": 1,
                "name": "hivex",
                "ref": "3b801940c0f8c11129805fe59590e0ee3aabb608",
            },
            {
                "arches": ["aarch64", "i686", "ppc64le", "s390x", "x86_64"],
                "buildorder": 2,
                "name": "qemu-kvm",
                "ref": "9cf15efa745c2df3f2968d58da9ed67b29b1300f",
            },
        ],
        "context": "9edba152",
        "distribution": {"name": "AlmaLinux", "version": "8"},
        "name": "virt-devel",
        "repository": {"arch": "x86_64", "name": "almalinux-8-powertools"},
        "stream": "rhel",
        "type": "module",
        "version": 8080020230712134837,
    }


@pytest.fixture
def beholder_slof_response():
    return {
        "distribution": {"name": "AlmaLinux", "version": "8"},
        "packages": {
            "exact": [
                {
                    "arch": "src",
                    "epoch": 0,
                    "name": "SLOF",
                    "release": "1.module_el8.6.0+2880+7d9e3703",
                    "repositories": [
                        {"arch": "src", "name": "almalinux-8-appstream"}
                    ],
                    "version": "20210217",
                },
                {
                    "arch": "noarch",
                    "epoch": 0,
                    "name": "SLOF",
                    "release": "1.module_el8.6.0+2880+7d9e3703",
                    "repositories": [
                        {"arch": "ppc64le", "name": "almalinux-8-appstream"}
                    ],
                    "version": "20210217",
                },
            ]
        },
        "sourcerpm": {
            "epoch": 0,
            "name": "SLOF",
            "release": "1.module_el8.6.0+2880+7d9e3703",
            "version": "20210217",
        },
        "type": "package",
    }


@pytest.fixture
def beholder_hivex_response():
    return {
        "distribution": {"name": "AlmaLinux", "version": "8"},
        "packages": {
            "closest": [
                {
                    "arch": "x86_64",
                    "epoch": 0,
                    "name": "hivex",
                    "release": "23.module_el8.6.0+2880+7d9e3703",
                    "repositories": [
                        {"arch": "x86_64", "name": "almalinux-8-appstream"}
                    ],
                    "version": "1.3.18",
                },
                {
                    "arch": "x86_64",
                    "epoch": 0,
                    "name": "hivex-devel",
                    "release": "23.module_el8.6.0+2880+7d9e3703",
                    "repositories": [
                        {"arch": "x86_64", "name": "almalinux-8-appstream"}
                    ],
                    "version": "1.3.18",
                },
                {
                    "arch": "x86_64",
                    "epoch": 0,
                    "name": "hivex-debuginfo",
                    "release": "23.module_el8.6.0+2880+7d9e3703",
                    "repositories": [
                        {
                            "arch": "x86_64",
                            "name": "almalinux-8-appstream-debuginfo",
                        }
                    ],
                    "version": "1.3.18",
                },
                {
                    "arch": "x86_64",
                    "epoch": 0,
                    "name": "hivex-debugsource",
                    "release": "23.module_el8.6.0+2880+7d9e3703",
                    "repositories": [
                        {
                            "arch": "x86_64",
                            "name": "almalinux-8-appstream-debuginfo",
                        }
                    ],
                    "version": "1.3.18",
                },
                {
                    "arch": "i686",
                    "epoch": 0,
                    "name": "hivex",
                    "release": "23.module_el8.6.0+2880+7d9e3703",
                    "repositories": [
                        {"arch": "x86_64", "name": "almalinux-8-powertools"}
                    ],
                    "version": "1.3.18",
                },
                {
                    "arch": "i686",
                    "epoch": 0,
                    "name": "hivex-devel",
                    "release": "23.module_el8.6.0+2880+7d9e3703",
                    "repositories": [
                        {"arch": "x86_64", "name": "almalinux-8-powertools"}
                    ],
                    "version": "1.3.18",
                },
                {
                    "arch": "i686",
                    "epoch": 0,
                    "name": "ocaml-hivex",
                    "release": "23.module_el8.6.0+2880+7d9e3703",
                    "repositories": [
                        {"arch": "x86_64", "name": "almalinux-8-powertools"}
                    ],
                    "version": "1.3.18",
                },
                {
                    "arch": "x86_64",
                    "epoch": 0,
                    "name": "ocaml-hivex",
                    "release": "23.module_el8.6.0+2880+7d9e3703",
                    "repositories": [
                        {"arch": "x86_64", "name": "almalinux-8-powertools"}
                    ],
                    "version": "1.3.18",
                },
                {
                    "arch": "i686",
                    "epoch": 0,
                    "name": "ocaml-hivex-devel",
                    "release": "23.module_el8.6.0+2880+7d9e3703",
                    "repositories": [
                        {"arch": "x86_64", "name": "almalinux-8-powertools"}
                    ],
                    "version": "1.3.18",
                },
                {
                    "arch": "x86_64",
                    "epoch": 0,
                    "name": "ocaml-hivex-devel",
                    "release": "23.module_el8.6.0+2880+7d9e3703",
                    "repositories": [
                        {"arch": "x86_64", "name": "almalinux-8-powertools"}
                    ],
                    "version": "1.3.18",
                },
                {
                    "arch": "i686",
                    "epoch": 0,
                    "name": "hivex-debuginfo",
                    "release": "23.module_el8.6.0+2880+7d9e3703",
                    "repositories": [
                        {
                            "arch": "x86_64",
                            "name": "almalinux-8-powertools-debuginfo",
                        }
                    ],
                    "version": "1.3.18",
                },
                {
                    "arch": "i686",
                    "epoch": 0,
                    "name": "hivex-debugsource",
                    "release": "23.module_el8.6.0+2880+7d9e3703",
                    "repositories": [
                        {
                            "arch": "x86_64",
                            "name": "almalinux-8-powertools-debuginfo",
                        }
                    ],
                    "version": "1.3.18",
                },
                {
                    "arch": "i686",
                    "epoch": 0,
                    "name": "ocaml-hivex-debuginfo",
                    "release": "23.module_el8.6.0+2880+7d9e3703",
                    "repositories": [
                        {
                            "arch": "x86_64",
                            "name": "almalinux-8-powertools-debuginfo",
                        }
                    ],
                    "version": "1.3.18",
                },
                {
                    "arch": "x86_64",
                    "epoch": 0,
                    "name": "ocaml-hivex-debuginfo",
                    "release": "23.module_el8.6.0+2880+7d9e3703",
                    "repositories": [
                        {
                            "arch": "x86_64",
                            "name": "almalinux-8-powertools-debuginfo",
                        }
                    ],
                    "version": "1.3.18",
                },
                {
                    "arch": "src",
                    "epoch": 0,
                    "name": "hivex",
                    "release": "23.module_el8.6.0+2880+7d9e3703",
                    "repositories": [
                        {"arch": "src", "name": "almalinux-8-appstream"}
                    ],
                    "version": "1.3.18",
                },
                {
                    "arch": "ppc64le",
                    "epoch": 0,
                    "name": "hivex",
                    "release": "23.module_el8.6.0+2880+7d9e3703",
                    "repositories": [
                        {"arch": "ppc64le", "name": "almalinux-8-appstream"}
                    ],
                    "version": "1.3.18",
                },
                {
                    "arch": "ppc64le",
                    "epoch": 0,
                    "name": "hivex-devel",
                    "release": "23.module_el8.6.0+2880+7d9e3703",
                    "repositories": [
                        {"arch": "ppc64le", "name": "almalinux-8-appstream"}
                    ],
                    "version": "1.3.18",
                },
                {
                    "arch": "ppc64le",
                    "epoch": 0,
                    "name": "hivex-debuginfo",
                    "release": "23.module_el8.6.0+2880+7d9e3703",
                    "repositories": [
                        {
                            "arch": "ppc64le",
                            "name": "almalinux-8-appstream-debuginfo",
                        }
                    ],
                    "version": "1.3.18",
                },
                {
                    "arch": "ppc64le",
                    "epoch": 0,
                    "name": "hivex-debugsource",
                    "release": "23.module_el8.6.0+2880+7d9e3703",
                    "repositories": [
                        {
                            "arch": "ppc64le",
                            "name": "almalinux-8-appstream-debuginfo",
                        }
                    ],
                    "version": "1.3.18",
                },
                {
                    "arch": "ppc64le",
                    "epoch": 0,
                    "name": "ocaml-hivex",
                    "release": "23.module_el8.6.0+2880+7d9e3703",
                    "repositories": [
                        {"arch": "ppc64le", "name": "almalinux-8-powertools"}
                    ],
                    "version": "1.3.18",
                },
                {
                    "arch": "ppc64le",
                    "epoch": 0,
                    "name": "ocaml-hivex-devel",
                    "release": "23.module_el8.6.0+2880+7d9e3703",
                    "repositories": [
                        {"arch": "ppc64le", "name": "almalinux-8-powertools"}
                    ],
                    "version": "1.3.18",
                },
                {
                    "arch": "ppc64le",
                    "epoch": 0,
                    "name": "ocaml-hivex-debuginfo",
                    "release": "23.module_el8.6.0+2880+7d9e3703",
                    "repositories": [
                        {
                            "arch": "ppc64le",
                            "name": "almalinux-8-powertools-debuginfo",
                        }
                    ],
                    "version": "1.3.18",
                },
            ]
        },
        "sourcerpm": {
            "epoch": 0,
            "name": "hivex",
            "release": "23.module_el8.6.0+2880+7d9e3703",
            "version": "1.3.18",
        },
        "type": "package",
    }


@pytest.fixture
def beholder_qemu_response():
    return {
        "distribution": {"name": "AlmaLinux", "version": "8"},
        "packages": {
            "closest": [
                {
                    "arch": "x86_64",
                    "epoch": 0,
                    "name": "qemu-kvm",
                    "release": "32.module_el8.8.0+3553+bd08596b",
                    "repositories": [
                        {"arch": "x86_64", "name": "almalinux-8-appstream"}
                    ],
                    "version": "6.2.0",
                },
                {
                    "arch": "x86_64",
                    "epoch": 0,
                    "name": "qemu-kvm-debuginfo",
                    "release": "32.module_el8.8.0+3553+bd08596b",
                    "repositories": [
                        {
                            "arch": "x86_64",
                            "name": "almalinux-8-appstream-debuginfo",
                        }
                    ],
                    "version": "6.2.0",
                },
                {
                    "arch": "x86_64",
                    "epoch": 0,
                    "name": "qemu-kvm-debugsource",
                    "release": "32.module_el8.8.0+3553+bd08596b",
                    "repositories": [
                        {
                            "arch": "x86_64",
                            "name": "almalinux-8-appstream-debuginfo",
                        }
                    ],
                    "version": "6.2.0",
                },
                {
                    "arch": "src",
                    "epoch": 0,
                    "name": "qemu-kvm",
                    "release": "32.module_el8.8.0+3553+bd08596b",
                    "repositories": [
                        {"arch": "src", "name": "almalinux-8-appstream"}
                    ],
                    "version": "6.2.0",
                },
                {
                    "arch": "ppc64le",
                    "epoch": 0,
                    "name": "qemu-kvm",
                    "release": "32.module_el8.8.0+3553+bd08596b",
                    "repositories": [
                        {"arch": "ppc64le", "name": "almalinux-8-appstream"}
                    ],
                    "version": "6.2.0",
                },
                {
                    "arch": "ppc64le",
                    "epoch": 0,
                    "name": "qemu-kvm-debuginfo",
                    "release": "32.module_el8.8.0+3553+bd08596b",
                    "repositories": [
                        {
                            "arch": "ppc64le",
                            "name": "almalinux-8-appstream-debuginfo",
                        }
                    ],
                    "version": "6.2.0",
                },
                {
                    "arch": "ppc64le",
                    "epoch": 0,
                    "name": "qemu-kvm-debugsource",
                    "release": "32.module_el8.8.0+3553+bd08596b",
                    "repositories": [
                        {
                            "arch": "ppc64le",
                            "name": "almalinux-8-appstream-debuginfo",
                        }
                    ],
                    "version": "6.2.0",
                },
            ]
        },
        "sourcerpm": {
            "epoch": 0,
            "name": "qemu-kvm",
            "release": "32.module_el8.8.0+3553+bd08596b",
            "version": "6.2.0",
        },
        "type": "package",
    }


@pytest.fixture
def beholder_ruby_response():
    return {
        "arch": "x86_64",
        "artifacts": [
            {
                "packages": [
                    {
                        "arch": "i686",
                        "epoch": 0,
                        "name": "ruby",
                        "release": "141.module_el8.7.0+3304+9392e77f",
                        "repositories": [
                            {"arch": "x86_64", "name": "almalinux-8-appstream"}
                        ],
                        "version": "3.1.2",
                    },
                    {
                        "arch": "src",
                        "epoch": 0,
                        "name": "ruby",
                        "release": "141.module_el8.7.0+3304+9392e77f",
                        "repositories": [
                            {"arch": "src", "name": "almalinux-8-appstream"}
                        ],
                        "version": "3.1.2",
                    },
                    {
                        "arch": "x86_64",
                        "epoch": 0,
                        "name": "ruby",
                        "release": "141.module_el8.7.0+3304+9392e77f",
                        "repositories": [
                            {"arch": "x86_64", "name": "almalinux-8-appstream"}
                        ],
                        "version": "3.1.2",
                    },
                    {
                        "arch": "i686",
                        "epoch": 0,
                        "name": "ruby-debuginfo",
                        "release": "141.module_el8.7.0+3304+9392e77f",
                        "repositories": [
                            {
                                "arch": "x86_64",
                                "name": "almalinux-8-appstream-debuginfo",
                            }
                        ],
                        "version": "3.1.2",
                    },
                    {
                        "arch": "x86_64",
                        "epoch": 0,
                        "name": "ruby-debuginfo",
                        "release": "141.module_el8.7.0+3304+9392e77f",
                        "repositories": [
                            {
                                "arch": "x86_64",
                                "name": "almalinux-8-appstream-debuginfo",
                            }
                        ],
                        "version": "3.1.2",
                    },
                    {
                        "arch": "i686",
                        "epoch": 0,
                        "name": "ruby-debugsource",
                        "release": "141.module_el8.7.0+3304+9392e77f",
                        "repositories": [
                            {
                                "arch": "x86_64",
                                "name": "almalinux-8-appstream-debuginfo",
                            }
                        ],
                        "version": "3.1.2",
                    },
                    {
                        "arch": "x86_64",
                        "epoch": 0,
                        "name": "ruby-debugsource",
                        "release": "141.module_el8.7.0+3304+9392e77f",
                        "repositories": [
                            {
                                "arch": "x86_64",
                                "name": "almalinux-8-appstream-debuginfo",
                            }
                        ],
                        "version": "3.1.2",
                    },
                    {
                        "arch": "i686",
                        "epoch": 0,
                        "name": "ruby-devel",
                        "release": "141.module_el8.7.0+3304+9392e77f",
                        "repositories": [
                            {"arch": "x86_64", "name": "almalinux-8-appstream"}
                        ],
                        "version": "3.1.2",
                    },
                    {
                        "arch": "x86_64",
                        "epoch": 0,
                        "name": "ruby-devel",
                        "release": "141.module_el8.7.0+3304+9392e77f",
                        "repositories": [
                            {"arch": "x86_64", "name": "almalinux-8-appstream"}
                        ],
                        "version": "3.1.2",
                    },
                    {
                        "arch": "noarch",
                        "epoch": 0,
                        "name": "rubygems",
                        "release": "141.module_el8.7.0+3304+9392e77f",
                        "repositories": [
                            {"arch": "x86_64", "name": "almalinux-8-appstream"}
                        ],
                        "version": "3.3.7",
                    },
                    {
                        "arch": "noarch",
                        "epoch": 0,
                        "name": "rubygems-devel",
                        "release": "141.module_el8.7.0+3304+9392e77f",
                        "repositories": [
                            {"arch": "x86_64", "name": "almalinux-8-appstream"}
                        ],
                        "version": "3.3.7",
                    },
                ],
                "sourcerpm": {
                    "epoch": 0,
                    "name": "ruby",
                    "release": "141.module_el8.7.0+3304+9392e77f",
                    "version": "3.1.2",
                },
            },
            {
                "packages": [
                    {
                        "arch": "src",
                        "epoch": 0,
                        "name": "rubygem-pg",
                        "release": "1.module_el8.7.0+3304+9392e77f",
                        "repositories": [
                            {"arch": "src", "name": "almalinux-8-appstream"}
                        ],
                        "version": "1.3.2",
                    },
                    {
                        "arch": "x86_64",
                        "epoch": 0,
                        "name": "rubygem-pg",
                        "release": "1.module_el8.7.0+3304+9392e77f",
                        "repositories": [
                            {"arch": "x86_64", "name": "almalinux-8-appstream"}
                        ],
                        "version": "1.3.2",
                    },
                    {
                        "arch": "x86_64",
                        "epoch": 0,
                        "name": "rubygem-pg-debuginfo",
                        "release": "1.module_el8.7.0+3304+9392e77f",
                        "repositories": [
                            {
                                "arch": "x86_64",
                                "name": "almalinux-8-appstream-debuginfo",
                            }
                        ],
                        "version": "1.3.2",
                    },
                    {
                        "arch": "x86_64",
                        "epoch": 0,
                        "name": "rubygem-pg-debugsource",
                        "release": "1.module_el8.7.0+3304+9392e77f",
                        "repositories": [
                            {
                                "arch": "x86_64",
                                "name": "almalinux-8-appstream-debuginfo",
                            }
                        ],
                        "version": "1.3.2",
                    },
                    {
                        "arch": "noarch",
                        "epoch": 0,
                        "name": "rubygem-pg-doc",
                        "release": "1.module_el8.7.0+3304+9392e77f",
                        "repositories": [
                            {"arch": "x86_64", "name": "almalinux-8-appstream"}
                        ],
                        "version": "1.3.2",
                    },
                ],
                "sourcerpm": {
                    "epoch": 0,
                    "name": "rubygem-pg",
                    "release": "1.module_el8.7.0+3304+9392e77f",
                    "version": "1.3.2",
                },
            },
        ],
        "components": [
            {
                "arches": ["aarch64", "i686", "ppc64le", "s390x", "x86_64"],
                "buildorder": 101,
                "name": "ruby",
                "ref": "8b6300061cdae180a557fe428e1222871494d44a",
            },
            {
                "arches": ["aarch64", "i686", "ppc64le", "s390x", "x86_64"],
                "buildorder": 102,
                "name": "rubygem-pg",
                "ref": "8e1861fdfbcfcd0ef40ded3de957231094e79565",
            },
        ],
        "context": "9edba152",
        "distribution": {"name": "AlmaLinux", "version": "8"},
        "name": "ruby",
        "repository": {"arch": "x86_64", "name": "almalinux-8-appstream"},
        "stream": "3.1",
        "type": "module",
        "version": 8070020221011155238,
    }


@pytest.fixture
def beholder_ruby_devel_response():
    return {
        "arch": "x86_64",
        "artifacts": [],
        "components": [
            {
                "arches": ["aarch64", "i686", "ppc64le", "s390x", "x86_64"],
                "buildorder": 101,
                "name": "ruby",
                "ref": "8b6300061cdae180a557fe428e1222871494d44a",
            },
            {
                "arches": ["aarch64", "i686", "ppc64le", "s390x", "x86_64"],
                "buildorder": 102,
                "name": "rubygem-pg",
                "ref": "8e1861fdfbcfcd0ef40ded3de957231094e79565",
            },
        ],
        "context": "9edba152",
        "distribution": {"name": "AlmaLinux", "version": "8"},
        "name": "ruby-devel",
        "repository": {"arch": "x86_64", "name": "almalinux-8-devel"},
        "stream": "3.1",
        "type": "module",
        "version": 8070020221011155238,
    }


@pytest.fixture
def beholder_ruby_package_response():
    return {
        "distribution": {"name": "AlmaLinux", "version": "8"},
        "packages": {
            "closest": [
                {
                    "arch": "aarch64",
                    "epoch": 0,
                    "name": "ruby",
                    "release": "141.module_el8.7.0+3304+9392e77f",
                    "repositories": [
                        {"arch": "aarch64", "name": "almalinux-8-appstream"}
                    ],
                    "version": "3.1.2",
                },
                {
                    "arch": "aarch64",
                    "epoch": 0,
                    "name": "ruby-devel",
                    "release": "141.module_el8.7.0+3304+9392e77f",
                    "repositories": [
                        {"arch": "aarch64", "name": "almalinux-8-appstream"}
                    ],
                    "version": "3.1.2",
                },
                {
                    "arch": "noarch",
                    "epoch": 0,
                    "name": "rubygems",
                    "release": "141.module_el8.7.0+3304+9392e77f",
                    "repositories": [
                        {"arch": "aarch64", "name": "almalinux-8-appstream"},
                        {"arch": "x86_64", "name": "almalinux-8-appstream"},
                    ],
                    "version": "3.3.7",
                },
                {
                    "arch": "noarch",
                    "epoch": 0,
                    "name": "rubygems-devel",
                    "release": "141.module_el8.7.0+3304+9392e77f",
                    "repositories": [
                        {"arch": "aarch64", "name": "almalinux-8-appstream"},
                        {"arch": "x86_64", "name": "almalinux-8-appstream"},
                    ],
                    "version": "3.3.7",
                },
                {
                    "arch": "aarch64",
                    "epoch": 0,
                    "name": "ruby-debuginfo",
                    "release": "141.module_el8.7.0+3304+9392e77f",
                    "repositories": [
                        {
                            "arch": "aarch64",
                            "name": "almalinux-8-appstream-debuginfo",
                        }
                    ],
                    "version": "3.1.2",
                },
                {
                    "arch": "aarch64",
                    "epoch": 0,
                    "name": "ruby-debugsource",
                    "release": "141.module_el8.7.0+3304+9392e77f",
                    "repositories": [
                        {
                            "arch": "aarch64",
                            "name": "almalinux-8-appstream-debuginfo",
                        }
                    ],
                    "version": "3.1.2",
                },
                {
                    "arch": "i686",
                    "epoch": 0,
                    "name": "ruby",
                    "release": "141.module_el8.7.0+3304+9392e77f",
                    "repositories": [
                        {"arch": "x86_64", "name": "almalinux-8-appstream"}
                    ],
                    "version": "3.1.2",
                },
                {
                    "arch": "x86_64",
                    "epoch": 0,
                    "name": "ruby",
                    "release": "141.module_el8.7.0+3304+9392e77f",
                    "repositories": [
                        {"arch": "x86_64", "name": "almalinux-8-appstream"}
                    ],
                    "version": "3.1.2",
                },
                {
                    "arch": "i686",
                    "epoch": 0,
                    "name": "ruby-devel",
                    "release": "141.module_el8.7.0+3304+9392e77f",
                    "repositories": [
                        {"arch": "x86_64", "name": "almalinux-8-appstream"}
                    ],
                    "version": "3.1.2",
                },
                {
                    "arch": "x86_64",
                    "epoch": 0,
                    "name": "ruby-devel",
                    "release": "141.module_el8.7.0+3304+9392e77f",
                    "repositories": [
                        {"arch": "x86_64", "name": "almalinux-8-appstream"}
                    ],
                    "version": "3.1.2",
                },
                {
                    "arch": "i686",
                    "epoch": 0,
                    "name": "ruby-debuginfo",
                    "release": "141.module_el8.7.0+3304+9392e77f",
                    "repositories": [
                        {
                            "arch": "x86_64",
                            "name": "almalinux-8-appstream-debuginfo",
                        }
                    ],
                    "version": "3.1.2",
                },
                {
                    "arch": "x86_64",
                    "epoch": 0,
                    "name": "ruby-debuginfo",
                    "release": "141.module_el8.7.0+3304+9392e77f",
                    "repositories": [
                        {
                            "arch": "x86_64",
                            "name": "almalinux-8-appstream-debuginfo",
                        }
                    ],
                    "version": "3.1.2",
                },
                {
                    "arch": "i686",
                    "epoch": 0,
                    "name": "ruby-debugsource",
                    "release": "141.module_el8.7.0+3304+9392e77f",
                    "repositories": [
                        {
                            "arch": "x86_64",
                            "name": "almalinux-8-appstream-debuginfo",
                        }
                    ],
                    "version": "3.1.2",
                },
                {
                    "arch": "x86_64",
                    "epoch": 0,
                    "name": "ruby-debugsource",
                    "release": "141.module_el8.7.0+3304+9392e77f",
                    "repositories": [
                        {
                            "arch": "x86_64",
                            "name": "almalinux-8-appstream-debuginfo",
                        }
                    ],
                    "version": "3.1.2",
                },
                {
                    "arch": "src",
                    "epoch": 0,
                    "name": "ruby",
                    "release": "141.module_el8.7.0+3304+9392e77f",
                    "repositories": [
                        {"arch": "src", "name": "almalinux-8-appstream"}
                    ],
                    "version": "3.1.2",
                },
            ]
        },
        "sourcerpm": {
            "epoch": 0,
            "name": "ruby",
            "release": "141.module_el8.7.0+3304+9392e77f",
            "version": "3.1.2",
        },
        "type": "package",
    }


@pytest.fixture
def beholder_rubygem_pg_response():
    return {
        "distribution": {"name": "AlmaLinux", "version": "8"},
        "packages": {"closest": []},
        "type": "package",
    }


@pytest.fixture
def beholder_subversion_response():
    return {
        "arch": "x86_64",
        "artifacts": [
            {
                "packages": [
                    {
                        "arch": "src",
                        "epoch": 0,
                        "name": "subversion",
                        "release": "5.module_el8.7.0+1146+633d65ff",
                        "repositories": [
                            {"arch": "src", "name": "almalinux-8-appstream"}
                        ],
                        "version": "1.10.2",
                    },
                    {
                        "arch": "x86_64",
                        "epoch": 0,
                        "name": "subversion",
                        "release": "5.module_el8.7.0+1146+633d65ff",
                        "repositories": [
                            {"arch": "x86_64", "name": "almalinux-8-appstream"}
                        ],
                        "version": "1.10.2",
                    },
                    {
                        "arch": "x86_64",
                        "epoch": 0,
                        "name": "subversion-devel",
                        "release": "5.module_el8.7.0+1146+633d65ff",
                        "repositories": [
                            {"arch": "x86_64", "name": "almalinux-8-appstream"}
                        ],
                        "version": "1.10.2",
                    },
                    {
                        "arch": "x86_64",
                        "epoch": 0,
                        "name": "subversion-debuginfo",
                        "release": "5.module_el8.7.0+1146+633d65ff",
                        "repositories": [],
                        "version": "1.10.2",
                    },
                    {
                        "arch": "x86_64",
                        "epoch": 0,
                        "name": "subversion-debugsource",
                        "release": "5.module_el8.7.0+1146+633d65ff",
                        "repositories": [],
                        "version": "1.10.2",
                    },
                ],
                "sourcerpm": {
                    "epoch": 0,
                    "name": "subversion",
                    "release": "5.module_el8.7.0+1146+633d65ff",
                    "version": "1.10.2",
                },
            },
        ],
        "components": [
            {
                "arches": ["aarch64", "i686", "ppc64le", "x86_64"],
                "buildorder": 20,
                "name": "subversion",
                "ref": "422d6ce5d5ac80f246ecaf58a6be1957d18a9147",
            }
        ],
        "context": "78111232",
        "distribution": {"name": "AlmaLinux", "version": "8"},
        "name": "subversion",
        "repository": {"arch": "x86_64", "name": "almalinux-8-appstream"},
        "stream": "1.10",
        "type": "module",
        "version": 8070020220711155714,
    }


@pytest.fixture
def beholder_subversion_devel_response():
    return {
        "arch": "x86_64",
        "artifacts": [
            {
                "packages": [
                    {
                        "arch": "i686",
                        "epoch": 0,
                        "name": "subversion",
                        "release": "5.module_el8.7.0+1146+633d65ff",
                        "repositories": [
                            {
                                "arch": "x86_64",
                                "name": "almalinux-8-powertools",
                            }
                        ],
                        "version": "1.10.2",
                    },
                    {
                        "arch": "i686",
                        "epoch": 0,
                        "name": "subversion-devel",
                        "release": "5.module_el8.7.0+1146+633d65ff",
                        "repositories": [
                            {
                                "arch": "x86_64",
                                "name": "almalinux-8-powertools",
                            }
                        ],
                        "version": "1.10.2",
                    },
                    {
                        "arch": "i686",
                        "epoch": 0,
                        "name": "subversion-ruby",
                        "release": "5.module_el8.7.0+1146+633d65ff",
                        "repositories": [
                            {
                                "arch": "x86_64",
                                "name": "almalinux-8-powertools",
                            }
                        ],
                        "version": "1.10.2",
                    },
                    {
                        "arch": "x86_64",
                        "epoch": 0,
                        "name": "subversion-ruby",
                        "release": "5.module_el8.7.0+1146+633d65ff",
                        "repositories": [
                            {
                                "arch": "x86_64",
                                "name": "almalinux-8-powertools",
                            }
                        ],
                        "version": "1.10.2",
                    },
                    {
                        "arch": "i686",
                        "epoch": 0,
                        "name": "subversion-debuginfo",
                        "release": "5.module_el8.7.0+1146+633d65ff",
                        "repositories": [
                            {
                                "arch": "x86_64",
                                "name": "almalinux-8-powertools-debuginfo",
                            }
                        ],
                        "version": "1.10.2",
                    },
                    {
                        "arch": "i686",
                        "epoch": 0,
                        "name": "subversion-debugsource",
                        "release": "5.module_el8.7.0+1146+633d65ff",
                        "repositories": [
                            {
                                "arch": "x86_64",
                                "name": "almalinux-8-powertools-debuginfo",
                            }
                        ],
                        "version": "1.10.2",
                    },
                ],
                "sourcerpm": {
                    "epoch": 0,
                    "name": "subversion",
                    "release": "5.module_el8.7.0+1146+633d65ff",
                    "version": "1.10.2",
                },
            },
        ],
        "components": [
            {
                "arches": ["aarch64", "i686", "ppc64le", "x86_64"],
                "buildorder": 20,
                "name": "subversion",
                "ref": "422d6ce5d5ac80f246ecaf58a6be1957d18a9147",
            }
        ],
        "context": "78111232",
        "distribution": {"name": "AlmaLinux", "version": "8"},
        "name": "subversion-devel",
        "repository": {"arch": "x86_64", "name": "almalinux-8-powertools"},
        "stream": "1.10",
        "type": "module",
        "version": 8070020220711155714,
    }


@pytest.fixture
def beholder_subversion_package_response():
    return {
        "distribution": {"name": "AlmaLinux", "version": "8"},
        "packages": {
            "closest": [
                {
                    "arch": "aarch64",
                    "epoch": 0,
                    "name": "subversion",
                    "release": "5.module_el8.7.0+1146+633d65ff",
                    "repositories": [
                        {"arch": "aarch64", "name": "almalinux-8-appstream"}
                    ],
                    "version": "1.10.2",
                },
                {
                    "arch": "aarch64",
                    "epoch": 0,
                    "name": "subversion-devel",
                    "release": "5.module_el8.7.0+1146+633d65ff",
                    "repositories": [
                        {"arch": "aarch64", "name": "almalinux-8-appstream"}
                    ],
                    "version": "1.10.2",
                },
                {
                    "arch": "aarch64",
                    "epoch": 0,
                    "name": "subversion-ruby",
                    "release": "5.module_el8.7.0+1146+633d65ff",
                    "repositories": [
                        {"arch": "aarch64", "name": "almalinux-8-powertools"}
                    ],
                    "version": "1.10.2",
                },
                {
                    "arch": "x86_64",
                    "epoch": 0,
                    "name": "subversion",
                    "release": "5.module_el8.7.0+1146+633d65ff",
                    "repositories": [
                        {"arch": "x86_64", "name": "almalinux-8-appstream"}
                    ],
                    "version": "1.10.2",
                },
                {
                    "arch": "x86_64",
                    "epoch": 0,
                    "name": "subversion-devel",
                    "release": "5.module_el8.7.0+1146+633d65ff",
                    "repositories": [
                        {"arch": "x86_64", "name": "almalinux-8-appstream"}
                    ],
                    "version": "1.10.2",
                },
                {
                    "arch": "i686",
                    "epoch": 0,
                    "name": "subversion",
                    "release": "5.module_el8.7.0+1146+633d65ff",
                    "repositories": [
                        {"arch": "x86_64", "name": "almalinux-8-powertools"}
                    ],
                    "version": "1.10.2",
                },
                {
                    "arch": "i686",
                    "epoch": 0,
                    "name": "subversion-devel",
                    "release": "5.module_el8.7.0+1146+633d65ff",
                    "repositories": [
                        {"arch": "x86_64", "name": "almalinux-8-powertools"}
                    ],
                    "version": "1.10.2",
                },
                {
                    "arch": "aarch64",
                    "epoch": 0,
                    "name": "subversion-debugsource",
                    "release": "5.module_el8.7.0+1146+633d65ff",
                    "repositories": [
                        {
                            "arch": "aarch64",
                            "name": "almalinux-8-appstream-debuginfo",
                        }
                    ],
                    "version": "1.10.2",
                },
                {
                    "arch": "x86_64",
                    "epoch": 0,
                    "name": "subversion-debugsource",
                    "release": "5.module_el8.7.0+1146+633d65ff",
                    "repositories": [
                        {
                            "arch": "x86_64",
                            "name": "almalinux-8-appstream-debuginfo",
                        }
                    ],
                    "version": "1.10.2",
                },
                {
                    "arch": "i686",
                    "epoch": 0,
                    "name": "subversion-debugsource",
                    "release": "5.module_el8.7.0+1146+633d65ff",
                    "repositories": [
                        {
                            "arch": "x86_64",
                            "name": "almalinux-8-appstream-debuginfo",
                        }
                    ],
                    "version": "1.10.2",
                },
                {
                    "arch": "aarch64",
                    "epoch": 0,
                    "name": "subversion-debuginfo",
                    "release": "5.module_el8.7.0+1146+633d65ff",
                    "repositories": [
                        {
                            "arch": "aarch64",
                            "name": "almalinux-8-appstream-debuginfo",
                        }
                    ],
                    "version": "1.10.2",
                },
                {
                    "arch": "x86_64",
                    "epoch": 0,
                    "name": "subversion-debuginfo",
                    "release": "5.module_el8.7.0+1146+633d65ff",
                    "repositories": [
                        {
                            "arch": "x86_64",
                            "name": "almalinux-8-appstream-debuginfo",
                        }
                    ],
                    "version": "1.10.2",
                },
                {
                    "arch": "i686",
                    "epoch": 0,
                    "name": "subversion-debuginfo",
                    "release": "5.module_el8.7.0+1146+633d65ff",
                    "repositories": [
                        {
                            "arch": "x86_64",
                            "name": "almalinux-8-appstream-debuginfo",
                        }
                    ],
                    "version": "1.10.2",
                },
                {
                    "arch": "i686",
                    "epoch": 0,
                    "name": "subversion-ruby",
                    "release": "5.module_el8.7.0+1146+633d65ff",
                    "repositories": [
                        {"arch": "x86_64", "name": "almalinux-8-powertools"}
                    ],
                    "version": "1.10.2",
                },
                {
                    "arch": "x86_64",
                    "epoch": 0,
                    "name": "subversion-ruby",
                    "release": "5.module_el8.7.0+1146+633d65ff",
                    "repositories": [
                        {"arch": "x86_64", "name": "almalinux-8-powertools"}
                    ],
                    "version": "1.10.2",
                },
                {
                    "arch": "src",
                    "epoch": 0,
                    "name": "subversion",
                    "release": "5.module_el8.7.0+1146+633d65ff",
                    "repositories": [
                        {"arch": "src", "name": "almalinux-8-appstream"}
                    ],
                    "version": "1.10.2",
                },
            ]
        },
        "sourcerpm": {
            "epoch": 0,
            "name": "subversion",
            "release": "5.module_el8.7.0+1146+633d65ff",
            "version": "1.10.2",
        },
        "type": "package",
    }


@pytest.fixture
def beholder_llvm_response():
    return {
        "arch": "x86_64",
        "artifacts": [
            {
                "packages": [
                    {
                        "arch": "i686",
                        "epoch": 0,
                        "name": "clang",
                        "release": "1.module+el8.6.0+14118+d530a951",
                        "repositories": [
                            {"arch": "x86_64", "name": "almalinux-8-appstream"}
                        ],
                        "version": "13.0.1",
                    },
                    {
                        "arch": "src",
                        "epoch": 0,
                        "name": "clang",
                        "release": "1.module+el8.6.0+14118+d530a951",
                        "repositories": [
                            {"arch": "src", "name": "almalinux-8-appstream"}
                        ],
                        "version": "13.0.1",
                    },
                    {
                        "arch": "x86_64",
                        "epoch": 0,
                        "name": "clang",
                        "release": "1.module+el8.6.0+14118+d530a951",
                        "repositories": [
                            {"arch": "x86_64", "name": "almalinux-8-appstream"}
                        ],
                        "version": "13.0.1",
                    },
                ],
                "sourcerpm": {
                    "epoch": 0,
                    "name": "clang",
                    "release": "1.module+el8.6.0+14118+d530a951",
                    "version": "13.0.1",
                },
            },
            {
                "packages": [
                    {
                        "arch": "i686",
                        "epoch": 0,
                        "name": "llvm",
                        "release": "1.module+el8.6.0+14118+d530a951",
                        "repositories": [
                            {"arch": "x86_64", "name": "almalinux-8-appstream"}
                        ],
                        "version": "13.0.1",
                    },
                    {
                        "arch": "src",
                        "epoch": 0,
                        "name": "llvm",
                        "release": "1.module+el8.6.0+14118+d530a951",
                        "repositories": [
                            {"arch": "src", "name": "almalinux-8-appstream"}
                        ],
                        "version": "13.0.1",
                    },
                    {
                        "arch": "x86_64",
                        "epoch": 0,
                        "name": "llvm",
                        "release": "1.module+el8.6.0+14118+d530a951",
                        "repositories": [
                            {"arch": "x86_64", "name": "almalinux-8-appstream"}
                        ],
                        "version": "13.0.1",
                    },
                ],
                "sourcerpm": {
                    "epoch": 0,
                    "name": "llvm",
                    "release": "1.module+el8.6.0+14118+d530a951",
                    "version": "13.0.1",
                },
            },
            {
                "packages": [
                    {
                        "arch": "i686",
                        "epoch": 0,
                        "name": "compiler-rt",
                        "release": "1.module+el8.6.0+14118+d530a951",
                        "repositories": [
                            {"arch": "x86_64", "name": "almalinux-8-appstream"}
                        ],
                        "version": "13.0.1",
                    },
                    {
                        "arch": "src",
                        "epoch": 0,
                        "name": "compiler-rt",
                        "release": "1.module+el8.6.0+14118+d530a951",
                        "repositories": [
                            {"arch": "src", "name": "almalinux-8-appstream"}
                        ],
                        "version": "13.0.1",
                    },
                    {
                        "arch": "x86_64",
                        "epoch": 0,
                        "name": "compiler-rt",
                        "release": "1.module+el8.6.0+14118+d530a951",
                        "repositories": [
                            {"arch": "x86_64", "name": "almalinux-8-appstream"}
                        ],
                        "version": "13.0.1",
                    },
                ],
                "sourcerpm": {
                    "epoch": 0,
                    "name": "compiler-rt",
                    "release": "1.module+el8.6.0+14118+d530a951",
                    "version": "13.0.1",
                },
            },
            {
                "packages": [
                    {
                        "arch": "noarch",
                        "epoch": 0,
                        "name": "python3-lit",
                        "release": "1.module+el8.6.0+14118+d530a951",
                        "repositories": [
                            {"arch": "x86_64", "name": "almalinux-8-appstream"}
                        ],
                        "version": "13.0.1",
                    },
                    {
                        "arch": "src",
                        "epoch": 0,
                        "name": "python-lit",
                        "release": "1.module+el8.6.0+14118+d530a951",
                        "repositories": [
                            {"arch": "src", "name": "almalinux-8-appstream"}
                        ],
                        "version": "13.0.1",
                    },
                ],
                "sourcerpm": {
                    "epoch": 0,
                    "name": "python-lit",
                    "release": "1.module+el8.6.0+14118+d530a951",
                    "version": "13.0.1",
                },
            },
        ],
        "components": [
            {
                "arches": ["aarch64", "i686", "ppc64le", "s390x", "x86_64"],
                "buildorder": 1,
                "name": "clang",
                "ref": "be957384a20cc280264d9e33925924d97557f7f5",
            },
            {
                "arches": ["aarch64", "i686", "ppc64le", "s390x", "x86_64"],
                "buildorder": 0,
                "name": "llvm",
                "ref": "379eb95ac2106298eaa546f7e18e6c7a6ae77f6d",
            },
            {
                "arches": ["aarch64", "i686", "ppc64le", "s390x", "x86_64"],
                "buildorder": 0,
                "name": "python-lit",
                "ref": "e6248214a5c6f8929607c13e8e10f64a95099e23",
            },
        ],
        "context": "9edba152",
        "distribution": {"name": "AlmaLinux", "version": "8"},
        "name": "llvm-toolset",
        "repository": {"arch": "x86_64", "name": "almalinux-8-appstream"},
        "stream": "rhel8",
        "type": "module",
        "version": 8080020230403095228,
    }


@pytest.fixture
def beholder_llvm_devel_response():
    return {
        "arch": "x86_64",
        "artifacts": [
            {
                "packages": [
                    {
                        "arch": "i686",
                        "epoch": 0,
                        "name": "clang",
                        "release": "1.module+el8.6.0+14118+d530a951",
                        "repositories": [
                            {"arch": "x86_64", "name": "almalinux-8-appstream"}
                        ],
                        "version": "13.0.1",
                    },
                ],
                "sourcerpm": {
                    "epoch": 0,
                    "name": "clang",
                    "release": "1.module+el8.6.0+14118+d530a951",
                    "version": "13.0.1",
                },
            },
            {
                "packages": [
                    {
                        "arch": "i686",
                        "epoch": 0,
                        "name": "llvm",
                        "release": "1.module+el8.6.0+14118+d530a951",
                        "repositories": [
                            {"arch": "x86_64", "name": "almalinux-8-appstream"}
                        ],
                        "version": "13.0.1",
                    },
                ],
                "sourcerpm": {
                    "epoch": 0,
                    "name": "llvm",
                    "release": "1.module+el8.6.0+14118+d530a951",
                    "version": "13.0.1",
                },
            },
        ],
        "components": [
            {
                "arches": ["aarch64", "i686", "ppc64le", "s390x", "x86_64"],
                "buildorder": 1,
                "name": "clang",
                "ref": "be957384a20cc280264d9e33925924d97557f7f5",
            },
            {
                "arches": ["aarch64", "i686", "ppc64le", "s390x", "x86_64"],
                "buildorder": 0,
                "name": "llvm",
                "ref": "379eb95ac2106298eaa546f7e18e6c7a6ae77f6d",
            },
            {
                "arches": ["aarch64", "i686", "ppc64le", "s390x", "x86_64"],
                "buildorder": 0,
                "name": "python-lit",
                "ref": "e6248214a5c6f8929607c13e8e10f64a95099e23",
            },
        ],
        "context": "9edba152",
        "distribution": {"name": "AlmaLinux", "version": "8"},
        "name": "llvm-toolset-devel",
        "repository": {"arch": "x86_64", "name": "almalinux-8-devel"},
        "stream": "rhel8",
        "type": "module",
        "version": 8080020230403095228,
    }


@pytest.fixture
@pytest.mark.anyio
def mock_beholder_call(
    monkeypatch,
    beholder_virt_response: dict,
    beholder_virt_devel_response: dict,
    beholder_slof_response: dict,
    beholder_hivex_response: dict,
    beholder_qemu_response: dict,
    beholder_rubygem_pg_response: dict,
    beholder_ruby_package_response: dict,
    beholder_ruby_devel_response: dict,
    beholder_ruby_response: dict,
    beholder_subversion_devel_response: dict,
    beholder_subversion_response: dict,
    beholder_subversion_package_response: dict,
    beholder_llvm_response: dict,
    beholder_llvm_devel_response: dict,
):
    async def func(*args, **kwargs):
        *_, endpoint = args
        response = {}
        if 'SLOF-20210217-1.module_el8.6.0+2880+7d9e3703.src.rpm' in endpoint:
            response = beholder_slof_response
        if 'hivex-1.3.18-23.module_el8.6.0+2880+7d9e3703.src.rpm' in endpoint:
            response = beholder_hivex_response
        if (
            'qemu-kvm-6.2.0-32.module_el8.8.0+3553+bd08596b.src.rpm'
            in endpoint
        ):
            response = beholder_qemu_response
        if '/module/virt/rhel/x86_64' in endpoint:
            response = beholder_virt_response
        if '/module/virt-devel/rhel/x86_64/' in endpoint:
            response = beholder_virt_devel_response
        if '/module/ruby/3.1/x86_64/' in endpoint:
            response = beholder_ruby_response
        if '/module/ruby-devel/3.1/x86_64/' in endpoint:
            response = beholder_ruby_package_response
        if 'ruby-3.1.2-141.module_el8.1.0+8+503f6fbd.src.rpm' in endpoint:
            response = beholder_ruby_devel_response
        if 'rubygem-pg-1.3.5-1.module_el8.1.0+8+503f6fbd.src.rpm' in endpoint:
            response = beholder_rubygem_pg_response
        if '/module/subversion-devel/1.10/x86_64/' in endpoint:
            response = beholder_subversion_devel_response
        if '/module/subversion/1.10/x86_64/' in endpoint:
            response = beholder_subversion_response
        if (
            'subversion-1.10.2-5.module_el8.6.0+3347+66c1e1d6.src.rpm'
            in endpoint
        ):
            response = beholder_subversion_package_response
        if '/module/llvm-toolset/rhel8/x86_64/' in endpoint:
            response = beholder_llvm_response
        if '/module/llvm-toolset-devel/rhel8/x86_64/' in endpoint:
            response = beholder_llvm_devel_response
        return copy.deepcopy(response)

    monkeypatch.setattr(BeholderClient, 'get', func)


@pytest.fixture
def get_multilib_packages_from_pulp(monkeypatch):
    def func(*args, **kwargs):
        *_, artifacts = args
        result = {}
        for artifact in artifacts:
            if isinstance(artifact, BuildTaskArtifact):
                nevra = parse_rpm_nevra(artifact.name)
                result[artifact.href] = RpmPackage(
                    name=nevra.name,
                    epoch=nevra.epoch,
                    version=nevra.version,
                    release=nevra.release,
                    arch=nevra.arch,
                )
        return result

    monkeypatch.setattr(MultilibProcessor, 'get_packages_info_from_pulp', func)

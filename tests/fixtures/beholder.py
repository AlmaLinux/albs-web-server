import pytest

from alws.models import BuildTaskArtifact
from alws.pulp_models import RpmPackage
from alws.schemas.build_node_schema import BuildDoneArtifact
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
                    {
                        "arch": "x86_64",
                        "epoch": 0,
                        "name": "perl-hivex",
                        "release": "23.module_el8.6.0+2880+7d9e3703",
                        "repositories": [
                            {"arch": "x86_64", "name": "almalinux-8-appstream"}
                        ],
                        "version": "1.3.18",
                    },
                    {
                        "arch": "x86_64",
                        "epoch": 0,
                        "name": "perl-hivex-debuginfo",
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
                        "name": "python3-hivex",
                        "release": "23.module_el8.6.0+2880+7d9e3703",
                        "repositories": [
                            {"arch": "x86_64", "name": "almalinux-8-appstream"}
                        ],
                        "version": "1.3.18",
                    },
                    {
                        "arch": "x86_64",
                        "epoch": 0,
                        "name": "python3-hivex-debuginfo",
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
                        "name": "ruby-hivex",
                        "release": "23.module_el8.6.0+2880+7d9e3703",
                        "repositories": [
                            {"arch": "x86_64", "name": "almalinux-8-appstream"}
                        ],
                        "version": "1.3.18",
                    },
                    {
                        "arch": "x86_64",
                        "epoch": 0,
                        "name": "ruby-hivex-debuginfo",
                        "release": "23.module_el8.6.0+2880+7d9e3703",
                        "repositories": [
                            {
                                "arch": "x86_64",
                                "name": "almalinux-8-appstream-debuginfo",
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
            {
                "packages": [
                    {
                        "arch": "src",
                        "epoch": 1,
                        "name": "libguestfs",
                        "release": "9.module_el8.7.0+3493+5ed0bd1c.alma",
                        "repositories": [],
                        "version": "1.44.0",
                    },
                    {
                        "arch": "x86_64",
                        "epoch": 1,
                        "name": "libguestfs",
                        "release": "9.module_el8.7.0+3493+5ed0bd1c.alma",
                        "repositories": [
                            {"arch": "x86_64", "name": "almalinux-8-appstream"}
                        ],
                        "version": "1.44.0",
                    },
                    {
                        "arch": "x86_64",
                        "epoch": 1,
                        "name": "libguestfs-appliance",
                        "release": "9.module_el8.7.0+3493+5ed0bd1c.alma",
                        "repositories": [
                            {"arch": "x86_64", "name": "almalinux-8-appstream"}
                        ],
                        "version": "1.44.0",
                    },
                    {
                        "arch": "noarch",
                        "epoch": 1,
                        "name": "libguestfs-bash-completion",
                        "release": "9.module_el8.7.0+3493+5ed0bd1c.alma",
                        "repositories": [
                            {"arch": "x86_64", "name": "almalinux-8-appstream"}
                        ],
                        "version": "1.44.0",
                    },
                    {
                        "arch": "x86_64",
                        "epoch": 1,
                        "name": "libguestfs-debuginfo",
                        "release": "9.module_el8.7.0+3493+5ed0bd1c.alma",
                        "repositories": [
                            {
                                "arch": "x86_64",
                                "name": "almalinux-8-appstream-debuginfo",
                            }
                        ],
                        "version": "1.44.0",
                    },
                    {
                        "arch": "x86_64",
                        "epoch": 1,
                        "name": "libguestfs-debugsource",
                        "release": "9.module_el8.7.0+3493+5ed0bd1c.alma",
                        "repositories": [
                            {
                                "arch": "x86_64",
                                "name": "almalinux-8-appstream-debuginfo",
                            }
                        ],
                        "version": "1.44.0",
                    },
                    {
                        "arch": "x86_64",
                        "epoch": 1,
                        "name": "libguestfs-devel",
                        "release": "9.module_el8.7.0+3493+5ed0bd1c.alma",
                        "repositories": [
                            {"arch": "x86_64", "name": "almalinux-8-appstream"}
                        ],
                        "version": "1.44.0",
                    },
                    {
                        "arch": "x86_64",
                        "epoch": 1,
                        "name": "libguestfs-gfs2",
                        "release": "9.module_el8.7.0+3493+5ed0bd1c.alma",
                        "repositories": [
                            {"arch": "x86_64", "name": "almalinux-8-appstream"}
                        ],
                        "version": "1.44.0",
                    },
                    {
                        "arch": "x86_64",
                        "epoch": 1,
                        "name": "libguestfs-gobject",
                        "release": "9.module_el8.7.0+3493+5ed0bd1c.alma",
                        "repositories": [
                            {"arch": "x86_64", "name": "almalinux-8-appstream"}
                        ],
                        "version": "1.44.0",
                    },
                    {
                        "arch": "x86_64",
                        "epoch": 1,
                        "name": "libguestfs-gobject-debuginfo",
                        "release": "9.module_el8.7.0+3493+5ed0bd1c.alma",
                        "repositories": [
                            {
                                "arch": "x86_64",
                                "name": "almalinux-8-appstream-debuginfo",
                            }
                        ],
                        "version": "1.44.0",
                    },
                    {
                        "arch": "x86_64",
                        "epoch": 1,
                        "name": "libguestfs-gobject-devel",
                        "release": "9.module_el8.7.0+3493+5ed0bd1c.alma",
                        "repositories": [
                            {"arch": "x86_64", "name": "almalinux-8-appstream"}
                        ],
                        "version": "1.44.0",
                    },
                    {
                        "arch": "noarch",
                        "epoch": 1,
                        "name": "libguestfs-inspect-icons",
                        "release": "9.module_el8.7.0+3493+5ed0bd1c.alma",
                        "repositories": [
                            {"arch": "x86_64", "name": "almalinux-8-appstream"}
                        ],
                        "version": "1.44.0",
                    },
                    {
                        "arch": "x86_64",
                        "epoch": 1,
                        "name": "libguestfs-java",
                        "release": "9.module_el8.7.0+3493+5ed0bd1c.alma",
                        "repositories": [
                            {"arch": "x86_64", "name": "almalinux-8-appstream"}
                        ],
                        "version": "1.44.0",
                    },
                    {
                        "arch": "x86_64",
                        "epoch": 1,
                        "name": "libguestfs-java-debuginfo",
                        "release": "9.module_el8.7.0+3493+5ed0bd1c.alma",
                        "repositories": [
                            {
                                "arch": "x86_64",
                                "name": "almalinux-8-appstream-debuginfo",
                            }
                        ],
                        "version": "1.44.0",
                    },
                    {
                        "arch": "x86_64",
                        "epoch": 1,
                        "name": "libguestfs-java-devel",
                        "release": "9.module_el8.7.0+3493+5ed0bd1c.alma",
                        "repositories": [
                            {"arch": "x86_64", "name": "almalinux-8-appstream"}
                        ],
                        "version": "1.44.0",
                    },
                    {
                        "arch": "noarch",
                        "epoch": 1,
                        "name": "libguestfs-javadoc",
                        "release": "9.module_el8.7.0+3493+5ed0bd1c.alma",
                        "repositories": [
                            {"arch": "x86_64", "name": "almalinux-8-appstream"}
                        ],
                        "version": "1.44.0",
                    },
                    {
                        "arch": "noarch",
                        "epoch": 1,
                        "name": "libguestfs-man-pages-ja",
                        "release": "9.module_el8.7.0+3493+5ed0bd1c.alma",
                        "repositories": [
                            {"arch": "x86_64", "name": "almalinux-8-appstream"}
                        ],
                        "version": "1.44.0",
                    },
                    {
                        "arch": "noarch",
                        "epoch": 1,
                        "name": "libguestfs-man-pages-uk",
                        "release": "9.module_el8.7.0+3493+5ed0bd1c.alma",
                        "repositories": [
                            {"arch": "x86_64", "name": "almalinux-8-appstream"}
                        ],
                        "version": "1.44.0",
                    },
                    {
                        "arch": "x86_64",
                        "epoch": 1,
                        "name": "libguestfs-rescue",
                        "release": "9.module_el8.7.0+3493+5ed0bd1c.alma",
                        "repositories": [
                            {"arch": "x86_64", "name": "almalinux-8-appstream"}
                        ],
                        "version": "1.44.0",
                    },
                    {
                        "arch": "x86_64",
                        "epoch": 1,
                        "name": "libguestfs-rsync",
                        "release": "9.module_el8.7.0+3493+5ed0bd1c.alma",
                        "repositories": [
                            {"arch": "x86_64", "name": "almalinux-8-appstream"}
                        ],
                        "version": "1.44.0",
                    },
                    {
                        "arch": "noarch",
                        "epoch": 1,
                        "name": "libguestfs-tools",
                        "release": "9.module_el8.7.0+3493+5ed0bd1c.alma",
                        "repositories": [
                            {"arch": "x86_64", "name": "almalinux-8-appstream"}
                        ],
                        "version": "1.44.0",
                    },
                    {
                        "arch": "x86_64",
                        "epoch": 1,
                        "name": "libguestfs-tools-c",
                        "release": "9.module_el8.7.0+3493+5ed0bd1c.alma",
                        "repositories": [
                            {"arch": "x86_64", "name": "almalinux-8-appstream"}
                        ],
                        "version": "1.44.0",
                    },
                    {
                        "arch": "x86_64",
                        "epoch": 1,
                        "name": "libguestfs-tools-c-debuginfo",
                        "release": "9.module_el8.7.0+3493+5ed0bd1c.alma",
                        "repositories": [
                            {
                                "arch": "x86_64",
                                "name": "almalinux-8-appstream-debuginfo",
                            }
                        ],
                        "version": "1.44.0",
                    },
                    {
                        "arch": "x86_64",
                        "epoch": 1,
                        "name": "libguestfs-xfs",
                        "release": "9.module_el8.7.0+3493+5ed0bd1c.alma",
                        "repositories": [
                            {"arch": "x86_64", "name": "almalinux-8-appstream"}
                        ],
                        "version": "1.44.0",
                    },
                    {
                        "arch": "x86_64",
                        "epoch": 1,
                        "name": "lua-guestfs",
                        "release": "9.module_el8.7.0+3493+5ed0bd1c.alma",
                        "repositories": [
                            {"arch": "x86_64", "name": "almalinux-8-appstream"}
                        ],
                        "version": "1.44.0",
                    },
                    {
                        "arch": "x86_64",
                        "epoch": 1,
                        "name": "lua-guestfs-debuginfo",
                        "release": "9.module_el8.7.0+3493+5ed0bd1c.alma",
                        "repositories": [
                            {
                                "arch": "x86_64",
                                "name": "almalinux-8-appstream-debuginfo",
                            }
                        ],
                        "version": "1.44.0",
                    },
                    {
                        "arch": "x86_64",
                        "epoch": 1,
                        "name": "perl-Sys-Guestfs",
                        "release": "9.module_el8.7.0+3493+5ed0bd1c.alma",
                        "repositories": [
                            {"arch": "x86_64", "name": "almalinux-8-appstream"}
                        ],
                        "version": "1.44.0",
                    },
                    {
                        "arch": "x86_64",
                        "epoch": 1,
                        "name": "perl-Sys-Guestfs-debuginfo",
                        "release": "9.module_el8.7.0+3493+5ed0bd1c.alma",
                        "repositories": [
                            {
                                "arch": "x86_64",
                                "name": "almalinux-8-appstream-debuginfo",
                            }
                        ],
                        "version": "1.44.0",
                    },
                    {
                        "arch": "x86_64",
                        "epoch": 1,
                        "name": "python3-libguestfs",
                        "release": "9.module_el8.7.0+3493+5ed0bd1c.alma",
                        "repositories": [
                            {"arch": "x86_64", "name": "almalinux-8-appstream"}
                        ],
                        "version": "1.44.0",
                    },
                    {
                        "arch": "x86_64",
                        "epoch": 1,
                        "name": "python3-libguestfs-debuginfo",
                        "release": "9.module_el8.7.0+3493+5ed0bd1c.alma",
                        "repositories": [
                            {
                                "arch": "x86_64",
                                "name": "almalinux-8-appstream-debuginfo",
                            }
                        ],
                        "version": "1.44.0",
                    },
                    {
                        "arch": "x86_64",
                        "epoch": 1,
                        "name": "ruby-libguestfs",
                        "release": "9.module_el8.7.0+3493+5ed0bd1c.alma",
                        "repositories": [
                            {"arch": "x86_64", "name": "almalinux-8-appstream"}
                        ],
                        "version": "1.44.0",
                    },
                    {
                        "arch": "x86_64",
                        "epoch": 1,
                        "name": "ruby-libguestfs-debuginfo",
                        "release": "9.module_el8.7.0+3493+5ed0bd1c.alma",
                        "repositories": [
                            {
                                "arch": "x86_64",
                                "name": "almalinux-8-appstream-debuginfo",
                            }
                        ],
                        "version": "1.44.0",
                    },
                    {
                        "arch": "x86_64",
                        "epoch": 1,
                        "name": "virt-dib",
                        "release": "9.module_el8.7.0+3493+5ed0bd1c.alma",
                        "repositories": [
                            {"arch": "x86_64", "name": "almalinux-8-appstream"}
                        ],
                        "version": "1.44.0",
                    },
                    {
                        "arch": "x86_64",
                        "epoch": 1,
                        "name": "virt-dib-debuginfo",
                        "release": "9.module_el8.7.0+3493+5ed0bd1c.alma",
                        "repositories": [
                            {
                                "arch": "x86_64",
                                "name": "almalinux-8-appstream-debuginfo",
                            }
                        ],
                        "version": "1.44.0",
                    },
                ],
                "sourcerpm": {
                    "epoch": 1,
                    "name": "libguestfs",
                    "release": "9.module_el8.7.0+3493+5ed0bd1c.alma",
                    "version": "1.44.0",
                },
            },
            {
                "packages": [
                    {
                        "arch": "src",
                        "epoch": 0,
                        "name": "libguestfs-winsupport",
                        "release": "1.module_el8.8.0+3485+7cffc4a3",
                        "repositories": [
                            {"arch": "src", "name": "almalinux-8-appstream"}
                        ],
                        "version": "8.8",
                    },
                    {
                        "arch": "x86_64",
                        "epoch": 0,
                        "name": "libguestfs-winsupport",
                        "release": "1.module_el8.8.0+3485+7cffc4a3",
                        "repositories": [
                            {"arch": "x86_64", "name": "almalinux-8-appstream"}
                        ],
                        "version": "8.8",
                    },
                ],
                "sourcerpm": {
                    "epoch": 0,
                    "name": "libguestfs-winsupport",
                    "release": "1.module_el8.8.0+3485+7cffc4a3",
                    "version": "8.8",
                },
            },
            {
                "packages": [
                    {
                        "arch": "src",
                        "epoch": 0,
                        "name": "libiscsi",
                        "release": "8.module_el8.6.0+2880+7d9e3703",
                        "repositories": [
                            {"arch": "src", "name": "almalinux-8-appstream"}
                        ],
                        "version": "1.18.0",
                    },
                    {
                        "arch": "x86_64",
                        "epoch": 0,
                        "name": "libiscsi",
                        "release": "8.module_el8.6.0+2880+7d9e3703",
                        "repositories": [
                            {"arch": "x86_64", "name": "almalinux-8-appstream"}
                        ],
                        "version": "1.18.0",
                    },
                    {
                        "arch": "x86_64",
                        "epoch": 0,
                        "name": "libiscsi-debuginfo",
                        "release": "8.module_el8.6.0+2880+7d9e3703",
                        "repositories": [
                            {
                                "arch": "x86_64",
                                "name": "almalinux-8-appstream-debuginfo",
                            }
                        ],
                        "version": "1.18.0",
                    },
                    {
                        "arch": "x86_64",
                        "epoch": 0,
                        "name": "libiscsi-debugsource",
                        "release": "8.module_el8.6.0+2880+7d9e3703",
                        "repositories": [
                            {
                                "arch": "x86_64",
                                "name": "almalinux-8-appstream-debuginfo",
                            }
                        ],
                        "version": "1.18.0",
                    },
                    {
                        "arch": "x86_64",
                        "epoch": 0,
                        "name": "libiscsi-devel",
                        "release": "8.module_el8.6.0+2880+7d9e3703",
                        "repositories": [
                            {"arch": "x86_64", "name": "almalinux-8-appstream"}
                        ],
                        "version": "1.18.0",
                    },
                    {
                        "arch": "x86_64",
                        "epoch": 0,
                        "name": "libiscsi-utils",
                        "release": "8.module_el8.6.0+2880+7d9e3703",
                        "repositories": [
                            {"arch": "x86_64", "name": "almalinux-8-appstream"}
                        ],
                        "version": "1.18.0",
                    },
                    {
                        "arch": "x86_64",
                        "epoch": 0,
                        "name": "libiscsi-utils-debuginfo",
                        "release": "8.module_el8.6.0+2880+7d9e3703",
                        "repositories": [
                            {
                                "arch": "x86_64",
                                "name": "almalinux-8-appstream-debuginfo",
                            }
                        ],
                        "version": "1.18.0",
                    },
                ],
                "sourcerpm": {
                    "epoch": 0,
                    "name": "libiscsi",
                    "release": "8.module_el8.6.0+2880+7d9e3703",
                    "version": "1.18.0",
                },
            },
            {
                "packages": [
                    {
                        "arch": "src",
                        "epoch": 0,
                        "name": "libnbd",
                        "release": "5.module_el8.6.0+2880+7d9e3703",
                        "repositories": [
                            {"arch": "src", "name": "almalinux-8-appstream"}
                        ],
                        "version": "1.6.0",
                    },
                    {
                        "arch": "x86_64",
                        "epoch": 0,
                        "name": "libnbd",
                        "release": "5.module_el8.6.0+2880+7d9e3703",
                        "repositories": [
                            {"arch": "x86_64", "name": "almalinux-8-appstream"}
                        ],
                        "version": "1.6.0",
                    },
                    {
                        "arch": "noarch",
                        "epoch": 0,
                        "name": "libnbd-bash-completion",
                        "release": "5.module_el8.6.0+2880+7d9e3703",
                        "repositories": [
                            {"arch": "x86_64", "name": "almalinux-8-appstream"}
                        ],
                        "version": "1.6.0",
                    },
                    {
                        "arch": "x86_64",
                        "epoch": 0,
                        "name": "libnbd-debuginfo",
                        "release": "5.module_el8.6.0+2880+7d9e3703",
                        "repositories": [
                            {
                                "arch": "x86_64",
                                "name": "almalinux-8-appstream-debuginfo",
                            }
                        ],
                        "version": "1.6.0",
                    },
                    {
                        "arch": "x86_64",
                        "epoch": 0,
                        "name": "libnbd-debugsource",
                        "release": "5.module_el8.6.0+2880+7d9e3703",
                        "repositories": [
                            {
                                "arch": "x86_64",
                                "name": "almalinux-8-appstream-debuginfo",
                            }
                        ],
                        "version": "1.6.0",
                    },
                    {
                        "arch": "x86_64",
                        "epoch": 0,
                        "name": "libnbd-devel",
                        "release": "5.module_el8.6.0+2880+7d9e3703",
                        "repositories": [
                            {"arch": "x86_64", "name": "almalinux-8-appstream"}
                        ],
                        "version": "1.6.0",
                    },
                    {
                        "arch": "x86_64",
                        "epoch": 0,
                        "name": "nbdfuse",
                        "release": "5.module_el8.6.0+2880+7d9e3703",
                        "repositories": [
                            {"arch": "x86_64", "name": "almalinux-8-appstream"}
                        ],
                        "version": "1.6.0",
                    },
                    {
                        "arch": "x86_64",
                        "epoch": 0,
                        "name": "nbdfuse-debuginfo",
                        "release": "5.module_el8.6.0+2880+7d9e3703",
                        "repositories": [
                            {
                                "arch": "x86_64",
                                "name": "almalinux-8-appstream-debuginfo",
                            }
                        ],
                        "version": "1.6.0",
                    },
                    {
                        "arch": "x86_64",
                        "epoch": 0,
                        "name": "python3-libnbd",
                        "release": "5.module_el8.6.0+2880+7d9e3703",
                        "repositories": [
                            {"arch": "x86_64", "name": "almalinux-8-appstream"}
                        ],
                        "version": "1.6.0",
                    },
                    {
                        "arch": "x86_64",
                        "epoch": 0,
                        "name": "python3-libnbd-debuginfo",
                        "release": "5.module_el8.6.0+2880+7d9e3703",
                        "repositories": [
                            {
                                "arch": "x86_64",
                                "name": "almalinux-8-appstream-debuginfo",
                            }
                        ],
                        "version": "1.6.0",
                    },
                ],
                "sourcerpm": {
                    "epoch": 0,
                    "name": "libnbd",
                    "release": "5.module_el8.6.0+2880+7d9e3703",
                    "version": "1.6.0",
                },
            },
            {
                "packages": [
                    {
                        "arch": "src",
                        "epoch": 0,
                        "name": "libtpms",
                        "release": "2.20211126git1ff6fe1f43.module_el8.8.0+3553+bd08596b",
                        "repositories": [
                            {"arch": "src", "name": "almalinux-8-appstream"}
                        ],
                        "version": "0.9.1",
                    },
                    {
                        "arch": "x86_64",
                        "epoch": 0,
                        "name": "libtpms",
                        "release": "2.20211126git1ff6fe1f43.module_el8.8.0+3553+bd08596b",
                        "repositories": [
                            {"arch": "x86_64", "name": "almalinux-8-appstream"}
                        ],
                        "version": "0.9.1",
                    },
                    {
                        "arch": "x86_64",
                        "epoch": 0,
                        "name": "libtpms-debuginfo",
                        "release": "2.20211126git1ff6fe1f43.module_el8.8.0+3553+bd08596b",
                        "repositories": [
                            {
                                "arch": "x86_64",
                                "name": "almalinux-8-appstream-debuginfo",
                            }
                        ],
                        "version": "0.9.1",
                    },
                    {
                        "arch": "x86_64",
                        "epoch": 0,
                        "name": "libtpms-debugsource",
                        "release": "2.20211126git1ff6fe1f43.module_el8.8.0+3553+bd08596b",
                        "repositories": [
                            {
                                "arch": "x86_64",
                                "name": "almalinux-8-appstream-debuginfo",
                            }
                        ],
                        "version": "0.9.1",
                    },
                    {
                        "arch": "x86_64",
                        "epoch": 0,
                        "name": "libtpms-devel",
                        "release": "2.20211126git1ff6fe1f43.module_el8.8.0+3553+bd08596b",
                        "repositories": [
                            {"arch": "x86_64", "name": "almalinux-8-appstream"}
                        ],
                        "version": "0.9.1",
                    },
                ],
                "sourcerpm": {
                    "epoch": 0,
                    "name": "libtpms",
                    "release": "2.20211126git1ff6fe1f43.module_el8.8.0+3553+bd08596b",
                    "version": "0.9.1",
                },
            },
            {
                "packages": [
                    {
                        "arch": "src",
                        "epoch": 0,
                        "name": "libvirt",
                        "release": "19.2.module_el8.8.0+3585+76b9c397.alma",
                        "repositories": [
                            {"arch": "src", "name": "almalinux-8-appstream"}
                        ],
                        "version": "8.0.0",
                    },
                    {
                        "arch": "x86_64",
                        "epoch": 0,
                        "name": "libvirt",
                        "release": "19.2.module_el8.8.0+3585+76b9c397.alma",
                        "repositories": [
                            {"arch": "x86_64", "name": "almalinux-8-appstream"}
                        ],
                        "version": "8.0.0",
                    },
                    {
                        "arch": "x86_64",
                        "epoch": 0,
                        "name": "libvirt-client",
                        "release": "19.2.module_el8.8.0+3585+76b9c397.alma",
                        "repositories": [
                            {"arch": "x86_64", "name": "almalinux-8-appstream"}
                        ],
                        "version": "8.0.0",
                    },
                    {
                        "arch": "x86_64",
                        "epoch": 0,
                        "name": "libvirt-client-debuginfo",
                        "release": "19.2.module_el8.8.0+3585+76b9c397.alma",
                        "repositories": [
                            {
                                "arch": "x86_64",
                                "name": "almalinux-8-appstream-debuginfo",
                            }
                        ],
                        "version": "8.0.0",
                    },
                    {
                        "arch": "x86_64",
                        "epoch": 0,
                        "name": "libvirt-daemon",
                        "release": "19.2.module_el8.8.0+3585+76b9c397.alma",
                        "repositories": [
                            {"arch": "x86_64", "name": "almalinux-8-appstream"}
                        ],
                        "version": "8.0.0",
                    },
                    {
                        "arch": "x86_64",
                        "epoch": 0,
                        "name": "libvirt-daemon-config-network",
                        "release": "19.2.module_el8.8.0+3585+76b9c397.alma",
                        "repositories": [
                            {"arch": "x86_64", "name": "almalinux-8-appstream"}
                        ],
                        "version": "8.0.0",
                    },
                    {
                        "arch": "x86_64",
                        "epoch": 0,
                        "name": "libvirt-daemon-config-nwfilter",
                        "release": "19.2.module_el8.8.0+3585+76b9c397.alma",
                        "repositories": [
                            {"arch": "x86_64", "name": "almalinux-8-appstream"}
                        ],
                        "version": "8.0.0",
                    },
                    {
                        "arch": "x86_64",
                        "epoch": 0,
                        "name": "libvirt-daemon-debuginfo",
                        "release": "19.2.module_el8.8.0+3585+76b9c397.alma",
                        "repositories": [
                            {
                                "arch": "x86_64",
                                "name": "almalinux-8-appstream-debuginfo",
                            }
                        ],
                        "version": "8.0.0",
                    },
                    {
                        "arch": "x86_64",
                        "epoch": 0,
                        "name": "libvirt-daemon-driver-interface",
                        "release": "19.2.module_el8.8.0+3585+76b9c397.alma",
                        "repositories": [
                            {"arch": "x86_64", "name": "almalinux-8-appstream"}
                        ],
                        "version": "8.0.0",
                    },
                    {
                        "arch": "x86_64",
                        "epoch": 0,
                        "name": "libvirt-daemon-driver-interface-debuginfo",
                        "release": "19.2.module_el8.8.0+3585+76b9c397.alma",
                        "repositories": [
                            {
                                "arch": "x86_64",
                                "name": "almalinux-8-appstream-debuginfo",
                            }
                        ],
                        "version": "8.0.0",
                    },
                    {
                        "arch": "x86_64",
                        "epoch": 0,
                        "name": "libvirt-daemon-driver-network",
                        "release": "19.2.module_el8.8.0+3585+76b9c397.alma",
                        "repositories": [
                            {"arch": "x86_64", "name": "almalinux-8-appstream"}
                        ],
                        "version": "8.0.0",
                    },
                    {
                        "arch": "x86_64",
                        "epoch": 0,
                        "name": "libvirt-daemon-driver-network-debuginfo",
                        "release": "19.2.module_el8.8.0+3585+76b9c397.alma",
                        "repositories": [
                            {
                                "arch": "x86_64",
                                "name": "almalinux-8-appstream-debuginfo",
                            }
                        ],
                        "version": "8.0.0",
                    },
                    {
                        "arch": "x86_64",
                        "epoch": 0,
                        "name": "libvirt-daemon-driver-nodedev",
                        "release": "19.2.module_el8.8.0+3585+76b9c397.alma",
                        "repositories": [
                            {"arch": "x86_64", "name": "almalinux-8-appstream"}
                        ],
                        "version": "8.0.0",
                    },
                    {
                        "arch": "x86_64",
                        "epoch": 0,
                        "name": "libvirt-daemon-driver-nodedev-debuginfo",
                        "release": "19.2.module_el8.8.0+3585+76b9c397.alma",
                        "repositories": [
                            {
                                "arch": "x86_64",
                                "name": "almalinux-8-appstream-debuginfo",
                            }
                        ],
                        "version": "8.0.0",
                    },
                    {
                        "arch": "x86_64",
                        "epoch": 0,
                        "name": "libvirt-daemon-driver-nwfilter",
                        "release": "19.2.module_el8.8.0+3585+76b9c397.alma",
                        "repositories": [
                            {"arch": "x86_64", "name": "almalinux-8-appstream"}
                        ],
                        "version": "8.0.0",
                    },
                    {
                        "arch": "x86_64",
                        "epoch": 0,
                        "name": "libvirt-daemon-driver-nwfilter-debuginfo",
                        "release": "19.2.module_el8.8.0+3585+76b9c397.alma",
                        "repositories": [
                            {
                                "arch": "x86_64",
                                "name": "almalinux-8-appstream-debuginfo",
                            }
                        ],
                        "version": "8.0.0",
                    },
                    {
                        "arch": "x86_64",
                        "epoch": 0,
                        "name": "libvirt-daemon-driver-qemu",
                        "release": "19.2.module_el8.8.0+3585+76b9c397.alma",
                        "repositories": [
                            {"arch": "x86_64", "name": "almalinux-8-appstream"}
                        ],
                        "version": "8.0.0",
                    },
                    {
                        "arch": "x86_64",
                        "epoch": 0,
                        "name": "libvirt-daemon-driver-qemu-debuginfo",
                        "release": "19.2.module_el8.8.0+3585+76b9c397.alma",
                        "repositories": [
                            {
                                "arch": "x86_64",
                                "name": "almalinux-8-appstream-debuginfo",
                            }
                        ],
                        "version": "8.0.0",
                    },
                    {
                        "arch": "x86_64",
                        "epoch": 0,
                        "name": "libvirt-daemon-driver-secret",
                        "release": "19.2.module_el8.8.0+3585+76b9c397.alma",
                        "repositories": [
                            {"arch": "x86_64", "name": "almalinux-8-appstream"}
                        ],
                        "version": "8.0.0",
                    },
                    {
                        "arch": "x86_64",
                        "epoch": 0,
                        "name": "libvirt-daemon-driver-secret-debuginfo",
                        "release": "19.2.module_el8.8.0+3585+76b9c397.alma",
                        "repositories": [
                            {
                                "arch": "x86_64",
                                "name": "almalinux-8-appstream-debuginfo",
                            }
                        ],
                        "version": "8.0.0",
                    },
                    {
                        "arch": "x86_64",
                        "epoch": 0,
                        "name": "libvirt-daemon-driver-storage",
                        "release": "19.2.module_el8.8.0+3585+76b9c397.alma",
                        "repositories": [
                            {"arch": "x86_64", "name": "almalinux-8-appstream"}
                        ],
                        "version": "8.0.0",
                    },
                    {
                        "arch": "x86_64",
                        "epoch": 0,
                        "name": "libvirt-daemon-driver-storage-core",
                        "release": "19.2.module_el8.8.0+3585+76b9c397.alma",
                        "repositories": [
                            {"arch": "x86_64", "name": "almalinux-8-appstream"}
                        ],
                        "version": "8.0.0",
                    },
                    {
                        "arch": "x86_64",
                        "epoch": 0,
                        "name": "libvirt-daemon-driver-storage-core-debuginfo",
                        "release": "19.2.module_el8.8.0+3585+76b9c397.alma",
                        "repositories": [
                            {
                                "arch": "x86_64",
                                "name": "almalinux-8-appstream-debuginfo",
                            }
                        ],
                        "version": "8.0.0",
                    },
                    {
                        "arch": "x86_64",
                        "epoch": 0,
                        "name": "libvirt-daemon-driver-storage-disk",
                        "release": "19.2.module_el8.8.0+3585+76b9c397.alma",
                        "repositories": [
                            {"arch": "x86_64", "name": "almalinux-8-appstream"}
                        ],
                        "version": "8.0.0",
                    },
                    {
                        "arch": "x86_64",
                        "epoch": 0,
                        "name": "libvirt-daemon-driver-storage-disk-debuginfo",
                        "release": "19.2.module_el8.8.0+3585+76b9c397.alma",
                        "repositories": [
                            {
                                "arch": "x86_64",
                                "name": "almalinux-8-appstream-debuginfo",
                            }
                        ],
                        "version": "8.0.0",
                    },
                    {
                        "arch": "x86_64",
                        "epoch": 0,
                        "name": "libvirt-daemon-driver-storage-gluster",
                        "release": "19.2.module_el8.8.0+3585+76b9c397.alma",
                        "repositories": [
                            {"arch": "x86_64", "name": "almalinux-8-appstream"}
                        ],
                        "version": "8.0.0",
                    },
                    {
                        "arch": "x86_64",
                        "epoch": 0,
                        "name": "libvirt-daemon-driver-storage-gluster-debuginfo",
                        "release": "19.2.module_el8.8.0+3585+76b9c397.alma",
                        "repositories": [
                            {
                                "arch": "x86_64",
                                "name": "almalinux-8-appstream-debuginfo",
                            }
                        ],
                        "version": "8.0.0",
                    },
                    {
                        "arch": "x86_64",
                        "epoch": 0,
                        "name": "libvirt-daemon-driver-storage-iscsi",
                        "release": "19.2.module_el8.8.0+3585+76b9c397.alma",
                        "repositories": [
                            {"arch": "x86_64", "name": "almalinux-8-appstream"}
                        ],
                        "version": "8.0.0",
                    },
                    {
                        "arch": "x86_64",
                        "epoch": 0,
                        "name": "libvirt-daemon-driver-storage-iscsi-debuginfo",
                        "release": "19.2.module_el8.8.0+3585+76b9c397.alma",
                        "repositories": [
                            {
                                "arch": "x86_64",
                                "name": "almalinux-8-appstream-debuginfo",
                            }
                        ],
                        "version": "8.0.0",
                    },
                    {
                        "arch": "x86_64",
                        "epoch": 0,
                        "name": "libvirt-daemon-driver-storage-iscsi-direct",
                        "release": "19.2.module_el8.8.0+3585+76b9c397.alma",
                        "repositories": [
                            {"arch": "x86_64", "name": "almalinux-8-appstream"}
                        ],
                        "version": "8.0.0",
                    },
                    {
                        "arch": "x86_64",
                        "epoch": 0,
                        "name": "libvirt-daemon-driver-storage-iscsi-direct-debuginfo",
                        "release": "19.2.module_el8.8.0+3585+76b9c397.alma",
                        "repositories": [
                            {
                                "arch": "x86_64",
                                "name": "almalinux-8-appstream-debuginfo",
                            }
                        ],
                        "version": "8.0.0",
                    },
                    {
                        "arch": "x86_64",
                        "epoch": 0,
                        "name": "libvirt-daemon-driver-storage-logical",
                        "release": "19.2.module_el8.8.0+3585+76b9c397.alma",
                        "repositories": [
                            {"arch": "x86_64", "name": "almalinux-8-appstream"}
                        ],
                        "version": "8.0.0",
                    },
                    {
                        "arch": "x86_64",
                        "epoch": 0,
                        "name": "libvirt-daemon-driver-storage-logical-debuginfo",
                        "release": "19.2.module_el8.8.0+3585+76b9c397.alma",
                        "repositories": [
                            {
                                "arch": "x86_64",
                                "name": "almalinux-8-appstream-debuginfo",
                            }
                        ],
                        "version": "8.0.0",
                    },
                    {
                        "arch": "x86_64",
                        "epoch": 0,
                        "name": "libvirt-daemon-driver-storage-mpath",
                        "release": "19.2.module_el8.8.0+3585+76b9c397.alma",
                        "repositories": [
                            {"arch": "x86_64", "name": "almalinux-8-appstream"}
                        ],
                        "version": "8.0.0",
                    },
                    {
                        "arch": "x86_64",
                        "epoch": 0,
                        "name": "libvirt-daemon-driver-storage-mpath-debuginfo",
                        "release": "19.2.module_el8.8.0+3585+76b9c397.alma",
                        "repositories": [
                            {
                                "arch": "x86_64",
                                "name": "almalinux-8-appstream-debuginfo",
                            }
                        ],
                        "version": "8.0.0",
                    },
                    {
                        "arch": "x86_64",
                        "epoch": 0,
                        "name": "libvirt-daemon-driver-storage-rbd",
                        "release": "19.2.module_el8.8.0+3585+76b9c397.alma",
                        "repositories": [
                            {"arch": "x86_64", "name": "almalinux-8-appstream"}
                        ],
                        "version": "8.0.0",
                    },
                    {
                        "arch": "x86_64",
                        "epoch": 0,
                        "name": "libvirt-daemon-driver-storage-rbd-debuginfo",
                        "release": "19.2.module_el8.8.0+3585+76b9c397.alma",
                        "repositories": [
                            {
                                "arch": "x86_64",
                                "name": "almalinux-8-appstream-debuginfo",
                            }
                        ],
                        "version": "8.0.0",
                    },
                    {
                        "arch": "x86_64",
                        "epoch": 0,
                        "name": "libvirt-daemon-driver-storage-scsi",
                        "release": "19.2.module_el8.8.0+3585+76b9c397.alma",
                        "repositories": [
                            {"arch": "x86_64", "name": "almalinux-8-appstream"}
                        ],
                        "version": "8.0.0",
                    },
                    {
                        "arch": "x86_64",
                        "epoch": 0,
                        "name": "libvirt-daemon-driver-storage-scsi-debuginfo",
                        "release": "19.2.module_el8.8.0+3585+76b9c397.alma",
                        "repositories": [
                            {
                                "arch": "x86_64",
                                "name": "almalinux-8-appstream-debuginfo",
                            }
                        ],
                        "version": "8.0.0",
                    },
                    {
                        "arch": "x86_64",
                        "epoch": 0,
                        "name": "libvirt-daemon-kvm",
                        "release": "19.2.module_el8.8.0+3585+76b9c397.alma",
                        "repositories": [
                            {"arch": "x86_64", "name": "almalinux-8-appstream"}
                        ],
                        "version": "8.0.0",
                    },
                    {
                        "arch": "x86_64",
                        "epoch": 0,
                        "name": "libvirt-debuginfo",
                        "release": "19.2.module_el8.8.0+3585+76b9c397.alma",
                        "repositories": [
                            {
                                "arch": "x86_64",
                                "name": "almalinux-8-appstream-debuginfo",
                            }
                        ],
                        "version": "8.0.0",
                    },
                    {
                        "arch": "x86_64",
                        "epoch": 0,
                        "name": "libvirt-debugsource",
                        "release": "19.2.module_el8.8.0+3585+76b9c397.alma",
                        "repositories": [
                            {
                                "arch": "x86_64",
                                "name": "almalinux-8-appstream-debuginfo",
                            }
                        ],
                        "version": "8.0.0",
                    },
                    {
                        "arch": "x86_64",
                        "epoch": 0,
                        "name": "libvirt-devel",
                        "release": "19.2.module_el8.8.0+3585+76b9c397.alma",
                        "repositories": [
                            {"arch": "x86_64", "name": "almalinux-8-appstream"}
                        ],
                        "version": "8.0.0",
                    },
                    {
                        "arch": "x86_64",
                        "epoch": 0,
                        "name": "libvirt-docs",
                        "release": "19.2.module_el8.8.0+3585+76b9c397.alma",
                        "repositories": [
                            {"arch": "x86_64", "name": "almalinux-8-appstream"}
                        ],
                        "version": "8.0.0",
                    },
                    {
                        "arch": "x86_64",
                        "epoch": 0,
                        "name": "libvirt-libs",
                        "release": "19.2.module_el8.8.0+3585+76b9c397.alma",
                        "repositories": [
                            {"arch": "x86_64", "name": "almalinux-8-appstream"}
                        ],
                        "version": "8.0.0",
                    },
                    {
                        "arch": "x86_64",
                        "epoch": 0,
                        "name": "libvirt-libs-debuginfo",
                        "release": "19.2.module_el8.8.0+3585+76b9c397.alma",
                        "repositories": [
                            {
                                "arch": "x86_64",
                                "name": "almalinux-8-appstream-debuginfo",
                            }
                        ],
                        "version": "8.0.0",
                    },
                    {
                        "arch": "x86_64",
                        "epoch": 0,
                        "name": "libvirt-lock-sanlock",
                        "release": "19.2.module_el8.8.0+3585+76b9c397.alma",
                        "repositories": [
                            {"arch": "x86_64", "name": "almalinux-8-appstream"}
                        ],
                        "version": "8.0.0",
                    },
                    {
                        "arch": "x86_64",
                        "epoch": 0,
                        "name": "libvirt-lock-sanlock-debuginfo",
                        "release": "19.2.module_el8.8.0+3585+76b9c397.alma",
                        "repositories": [
                            {
                                "arch": "x86_64",
                                "name": "almalinux-8-appstream-debuginfo",
                            }
                        ],
                        "version": "8.0.0",
                    },
                    {
                        "arch": "x86_64",
                        "epoch": 0,
                        "name": "libvirt-nss",
                        "release": "19.2.module_el8.8.0+3585+76b9c397.alma",
                        "repositories": [
                            {"arch": "x86_64", "name": "almalinux-8-appstream"}
                        ],
                        "version": "8.0.0",
                    },
                    {
                        "arch": "x86_64",
                        "epoch": 0,
                        "name": "libvirt-nss-debuginfo",
                        "release": "19.2.module_el8.8.0+3585+76b9c397.alma",
                        "repositories": [
                            {
                                "arch": "x86_64",
                                "name": "almalinux-8-appstream-debuginfo",
                            }
                        ],
                        "version": "8.0.0",
                    },
                    {
                        "arch": "x86_64",
                        "epoch": 0,
                        "name": "libvirt-wireshark",
                        "release": "19.2.module_el8.8.0+3585+76b9c397.alma",
                        "repositories": [
                            {"arch": "x86_64", "name": "almalinux-8-appstream"}
                        ],
                        "version": "8.0.0",
                    },
                    {
                        "arch": "x86_64",
                        "epoch": 0,
                        "name": "libvirt-wireshark-debuginfo",
                        "release": "19.2.module_el8.8.0+3585+76b9c397.alma",
                        "repositories": [
                            {
                                "arch": "x86_64",
                                "name": "almalinux-8-appstream-debuginfo",
                            }
                        ],
                        "version": "8.0.0",
                    },
                ],
                "sourcerpm": {
                    "epoch": 0,
                    "name": "libvirt",
                    "release": "19.2.module_el8.8.0+3585+76b9c397.alma",
                    "version": "8.0.0",
                },
            },
            {
                "packages": [
                    {
                        "arch": "src",
                        "epoch": 0,
                        "name": "libvirt-dbus",
                        "release": "2.module_el8.6.0+2880+7d9e3703",
                        "repositories": [
                            {"arch": "src", "name": "almalinux-8-appstream"}
                        ],
                        "version": "1.3.0",
                    },
                    {
                        "arch": "x86_64",
                        "epoch": 0,
                        "name": "libvirt-dbus",
                        "release": "2.module_el8.6.0+2880+7d9e3703",
                        "repositories": [
                            {"arch": "x86_64", "name": "almalinux-8-appstream"}
                        ],
                        "version": "1.3.0",
                    },
                    {
                        "arch": "x86_64",
                        "epoch": 0,
                        "name": "libvirt-dbus-debuginfo",
                        "release": "2.module_el8.6.0+2880+7d9e3703",
                        "repositories": [
                            {
                                "arch": "x86_64",
                                "name": "almalinux-8-appstream-debuginfo",
                            }
                        ],
                        "version": "1.3.0",
                    },
                    {
                        "arch": "x86_64",
                        "epoch": 0,
                        "name": "libvirt-dbus-debugsource",
                        "release": "2.module_el8.6.0+2880+7d9e3703",
                        "repositories": [
                            {
                                "arch": "x86_64",
                                "name": "almalinux-8-appstream-debuginfo",
                            }
                        ],
                        "version": "1.3.0",
                    },
                ],
                "sourcerpm": {
                    "epoch": 0,
                    "name": "libvirt-dbus",
                    "release": "2.module_el8.6.0+2880+7d9e3703",
                    "version": "1.3.0",
                },
            },
            {
                "packages": [
                    {
                        "arch": "src",
                        "epoch": 0,
                        "name": "libvirt-python",
                        "release": "2.module_el8.7.0+3346+68867adb",
                        "repositories": [
                            {"arch": "src", "name": "almalinux-8-appstream"}
                        ],
                        "version": "8.0.0",
                    },
                    {
                        "arch": "x86_64",
                        "epoch": 0,
                        "name": "libvirt-python-debugsource",
                        "release": "2.module_el8.7.0+3346+68867adb",
                        "repositories": [
                            {
                                "arch": "x86_64",
                                "name": "almalinux-8-appstream-debuginfo",
                            }
                        ],
                        "version": "8.0.0",
                    },
                    {
                        "arch": "x86_64",
                        "epoch": 0,
                        "name": "python3-libvirt",
                        "release": "2.module_el8.7.0+3346+68867adb",
                        "repositories": [
                            {"arch": "x86_64", "name": "almalinux-8-appstream"}
                        ],
                        "version": "8.0.0",
                    },
                    {
                        "arch": "x86_64",
                        "epoch": 0,
                        "name": "python3-libvirt-debuginfo",
                        "release": "2.module_el8.7.0+3346+68867adb",
                        "repositories": [
                            {
                                "arch": "x86_64",
                                "name": "almalinux-8-appstream-debuginfo",
                            }
                        ],
                        "version": "8.0.0",
                    },
                ],
                "sourcerpm": {
                    "epoch": 0,
                    "name": "libvirt-python",
                    "release": "2.module_el8.7.0+3346+68867adb",
                    "version": "8.0.0",
                },
            },
            {
                "packages": [
                    {
                        "arch": "src",
                        "epoch": 0,
                        "name": "nbdkit",
                        "release": "5.module_el8.8.0+3485+7cffc4a3",
                        "repositories": [
                            {"arch": "src", "name": "almalinux-8-appstream"}
                        ],
                        "version": "1.24.0",
                    },
                    {
                        "arch": "x86_64",
                        "epoch": 0,
                        "name": "nbdkit",
                        "release": "5.module_el8.8.0+3485+7cffc4a3",
                        "repositories": [
                            {"arch": "x86_64", "name": "almalinux-8-appstream"}
                        ],
                        "version": "1.24.0",
                    },
                    {
                        "arch": "noarch",
                        "epoch": 0,
                        "name": "nbdkit-bash-completion",
                        "release": "5.module_el8.8.0+3485+7cffc4a3",
                        "repositories": [
                            {"arch": "x86_64", "name": "almalinux-8-appstream"}
                        ],
                        "version": "1.24.0",
                    },
                    {
                        "arch": "x86_64",
                        "epoch": 0,
                        "name": "nbdkit-basic-filters",
                        "release": "5.module_el8.8.0+3485+7cffc4a3",
                        "repositories": [
                            {"arch": "x86_64", "name": "almalinux-8-appstream"}
                        ],
                        "version": "1.24.0",
                    },
                    {
                        "arch": "x86_64",
                        "epoch": 0,
                        "name": "nbdkit-basic-filters-debuginfo",
                        "release": "5.module_el8.8.0+3485+7cffc4a3",
                        "repositories": [
                            {
                                "arch": "x86_64",
                                "name": "almalinux-8-appstream-debuginfo",
                            }
                        ],
                        "version": "1.24.0",
                    },
                    {
                        "arch": "x86_64",
                        "epoch": 0,
                        "name": "nbdkit-basic-plugins",
                        "release": "5.module_el8.8.0+3485+7cffc4a3",
                        "repositories": [
                            {"arch": "x86_64", "name": "almalinux-8-appstream"}
                        ],
                        "version": "1.24.0",
                    },
                    {
                        "arch": "x86_64",
                        "epoch": 0,
                        "name": "nbdkit-basic-plugins-debuginfo",
                        "release": "5.module_el8.8.0+3485+7cffc4a3",
                        "repositories": [
                            {
                                "arch": "x86_64",
                                "name": "almalinux-8-appstream-debuginfo",
                            }
                        ],
                        "version": "1.24.0",
                    },
                    {
                        "arch": "x86_64",
                        "epoch": 0,
                        "name": "nbdkit-curl-plugin",
                        "release": "5.module_el8.8.0+3485+7cffc4a3",
                        "repositories": [
                            {"arch": "x86_64", "name": "almalinux-8-appstream"}
                        ],
                        "version": "1.24.0",
                    },
                    {
                        "arch": "x86_64",
                        "epoch": 0,
                        "name": "nbdkit-curl-plugin-debuginfo",
                        "release": "5.module_el8.8.0+3485+7cffc4a3",
                        "repositories": [
                            {
                                "arch": "x86_64",
                                "name": "almalinux-8-appstream-debuginfo",
                            }
                        ],
                        "version": "1.24.0",
                    },
                    {
                        "arch": "x86_64",
                        "epoch": 0,
                        "name": "nbdkit-debuginfo",
                        "release": "5.module_el8.8.0+3485+7cffc4a3",
                        "repositories": [
                            {
                                "arch": "x86_64",
                                "name": "almalinux-8-appstream-debuginfo",
                            }
                        ],
                        "version": "1.24.0",
                    },
                    {
                        "arch": "x86_64",
                        "epoch": 0,
                        "name": "nbdkit-debugsource",
                        "release": "5.module_el8.8.0+3485+7cffc4a3",
                        "repositories": [
                            {
                                "arch": "x86_64",
                                "name": "almalinux-8-appstream-debuginfo",
                            }
                        ],
                        "version": "1.24.0",
                    },
                    {
                        "arch": "x86_64",
                        "epoch": 0,
                        "name": "nbdkit-devel",
                        "release": "5.module_el8.8.0+3485+7cffc4a3",
                        "repositories": [
                            {"arch": "x86_64", "name": "almalinux-8-appstream"}
                        ],
                        "version": "1.24.0",
                    },
                    {
                        "arch": "x86_64",
                        "epoch": 0,
                        "name": "nbdkit-example-plugins",
                        "release": "5.module_el8.8.0+3485+7cffc4a3",
                        "repositories": [
                            {"arch": "x86_64", "name": "almalinux-8-appstream"}
                        ],
                        "version": "1.24.0",
                    },
                    {
                        "arch": "x86_64",
                        "epoch": 0,
                        "name": "nbdkit-example-plugins-debuginfo",
                        "release": "5.module_el8.8.0+3485+7cffc4a3",
                        "repositories": [
                            {
                                "arch": "x86_64",
                                "name": "almalinux-8-appstream-debuginfo",
                            }
                        ],
                        "version": "1.24.0",
                    },
                    {
                        "arch": "x86_64",
                        "epoch": 0,
                        "name": "nbdkit-gzip-filter",
                        "release": "5.module_el8.8.0+3485+7cffc4a3",
                        "repositories": [
                            {"arch": "x86_64", "name": "almalinux-8-appstream"}
                        ],
                        "version": "1.24.0",
                    },
                    {
                        "arch": "x86_64",
                        "epoch": 0,
                        "name": "nbdkit-gzip-filter-debuginfo",
                        "release": "5.module_el8.8.0+3485+7cffc4a3",
                        "repositories": [
                            {
                                "arch": "x86_64",
                                "name": "almalinux-8-appstream-debuginfo",
                            }
                        ],
                        "version": "1.24.0",
                    },
                    {
                        "arch": "x86_64",
                        "epoch": 0,
                        "name": "nbdkit-gzip-plugin",
                        "release": "5.module_el8.8.0+3485+7cffc4a3",
                        "repositories": [
                            {"arch": "x86_64", "name": "almalinux-8-appstream"}
                        ],
                        "version": "1.24.0",
                    },
                    {
                        "arch": "x86_64",
                        "epoch": 0,
                        "name": "nbdkit-gzip-plugin-debuginfo",
                        "release": "5.module_el8.8.0+3485+7cffc4a3",
                        "repositories": [
                            {
                                "arch": "x86_64",
                                "name": "almalinux-8-appstream-debuginfo",
                            }
                        ],
                        "version": "1.24.0",
                    },
                    {
                        "arch": "x86_64",
                        "epoch": 0,
                        "name": "nbdkit-linuxdisk-plugin",
                        "release": "5.module_el8.8.0+3485+7cffc4a3",
                        "repositories": [
                            {"arch": "x86_64", "name": "almalinux-8-appstream"}
                        ],
                        "version": "1.24.0",
                    },
                    {
                        "arch": "x86_64",
                        "epoch": 0,
                        "name": "nbdkit-linuxdisk-plugin-debuginfo",
                        "release": "5.module_el8.8.0+3485+7cffc4a3",
                        "repositories": [
                            {
                                "arch": "x86_64",
                                "name": "almalinux-8-appstream-debuginfo",
                            }
                        ],
                        "version": "1.24.0",
                    },
                    {
                        "arch": "x86_64",
                        "epoch": 0,
                        "name": "nbdkit-nbd-plugin",
                        "release": "5.module_el8.8.0+3485+7cffc4a3",
                        "repositories": [
                            {"arch": "x86_64", "name": "almalinux-8-appstream"}
                        ],
                        "version": "1.24.0",
                    },
                    {
                        "arch": "x86_64",
                        "epoch": 0,
                        "name": "nbdkit-nbd-plugin-debuginfo",
                        "release": "5.module_el8.8.0+3485+7cffc4a3",
                        "repositories": [
                            {
                                "arch": "x86_64",
                                "name": "almalinux-8-appstream-debuginfo",
                            }
                        ],
                        "version": "1.24.0",
                    },
                    {
                        "arch": "x86_64",
                        "epoch": 0,
                        "name": "nbdkit-python-plugin",
                        "release": "5.module_el8.8.0+3485+7cffc4a3",
                        "repositories": [
                            {"arch": "x86_64", "name": "almalinux-8-appstream"}
                        ],
                        "version": "1.24.0",
                    },
                    {
                        "arch": "x86_64",
                        "epoch": 0,
                        "name": "nbdkit-python-plugin-debuginfo",
                        "release": "5.module_el8.8.0+3485+7cffc4a3",
                        "repositories": [
                            {
                                "arch": "x86_64",
                                "name": "almalinux-8-appstream-debuginfo",
                            }
                        ],
                        "version": "1.24.0",
                    },
                    {
                        "arch": "x86_64",
                        "epoch": 0,
                        "name": "nbdkit-server",
                        "release": "5.module_el8.8.0+3485+7cffc4a3",
                        "repositories": [
                            {"arch": "x86_64", "name": "almalinux-8-appstream"}
                        ],
                        "version": "1.24.0",
                    },
                    {
                        "arch": "x86_64",
                        "epoch": 0,
                        "name": "nbdkit-server-debuginfo",
                        "release": "5.module_el8.8.0+3485+7cffc4a3",
                        "repositories": [
                            {
                                "arch": "x86_64",
                                "name": "almalinux-8-appstream-debuginfo",
                            }
                        ],
                        "version": "1.24.0",
                    },
                    {
                        "arch": "x86_64",
                        "epoch": 0,
                        "name": "nbdkit-ssh-plugin",
                        "release": "5.module_el8.8.0+3485+7cffc4a3",
                        "repositories": [
                            {"arch": "x86_64", "name": "almalinux-8-appstream"}
                        ],
                        "version": "1.24.0",
                    },
                    {
                        "arch": "x86_64",
                        "epoch": 0,
                        "name": "nbdkit-ssh-plugin-debuginfo",
                        "release": "5.module_el8.8.0+3485+7cffc4a3",
                        "repositories": [
                            {
                                "arch": "x86_64",
                                "name": "almalinux-8-appstream-debuginfo",
                            }
                        ],
                        "version": "1.24.0",
                    },
                    {
                        "arch": "x86_64",
                        "epoch": 0,
                        "name": "nbdkit-tar-filter",
                        "release": "5.module_el8.8.0+3485+7cffc4a3",
                        "repositories": [
                            {"arch": "x86_64", "name": "almalinux-8-appstream"}
                        ],
                        "version": "1.24.0",
                    },
                    {
                        "arch": "x86_64",
                        "epoch": 0,
                        "name": "nbdkit-tar-filter-debuginfo",
                        "release": "5.module_el8.8.0+3485+7cffc4a3",
                        "repositories": [
                            {
                                "arch": "x86_64",
                                "name": "almalinux-8-appstream-debuginfo",
                            }
                        ],
                        "version": "1.24.0",
                    },
                    {
                        "arch": "x86_64",
                        "epoch": 0,
                        "name": "nbdkit-tar-plugin",
                        "release": "5.module_el8.8.0+3485+7cffc4a3",
                        "repositories": [
                            {"arch": "x86_64", "name": "almalinux-8-appstream"}
                        ],
                        "version": "1.24.0",
                    },
                    {
                        "arch": "x86_64",
                        "epoch": 0,
                        "name": "nbdkit-tar-plugin-debuginfo",
                        "release": "5.module_el8.8.0+3485+7cffc4a3",
                        "repositories": [
                            {
                                "arch": "x86_64",
                                "name": "almalinux-8-appstream-debuginfo",
                            }
                        ],
                        "version": "1.24.0",
                    },
                    {
                        "arch": "x86_64",
                        "epoch": 0,
                        "name": "nbdkit-tmpdisk-plugin",
                        "release": "5.module_el8.8.0+3485+7cffc4a3",
                        "repositories": [
                            {"arch": "x86_64", "name": "almalinux-8-appstream"}
                        ],
                        "version": "1.24.0",
                    },
                    {
                        "arch": "x86_64",
                        "epoch": 0,
                        "name": "nbdkit-tmpdisk-plugin-debuginfo",
                        "release": "5.module_el8.8.0+3485+7cffc4a3",
                        "repositories": [
                            {
                                "arch": "x86_64",
                                "name": "almalinux-8-appstream-debuginfo",
                            }
                        ],
                        "version": "1.24.0",
                    },
                    {
                        "arch": "x86_64",
                        "epoch": 0,
                        "name": "nbdkit-vddk-plugin",
                        "release": "5.module_el8.8.0+3485+7cffc4a3",
                        "repositories": [
                            {"arch": "x86_64", "name": "almalinux-8-appstream"}
                        ],
                        "version": "1.24.0",
                    },
                    {
                        "arch": "x86_64",
                        "epoch": 0,
                        "name": "nbdkit-vddk-plugin-debuginfo",
                        "release": "5.module_el8.8.0+3485+7cffc4a3",
                        "repositories": [
                            {
                                "arch": "x86_64",
                                "name": "almalinux-8-appstream-debuginfo",
                            }
                        ],
                        "version": "1.24.0",
                    },
                    {
                        "arch": "x86_64",
                        "epoch": 0,
                        "name": "nbdkit-xz-filter",
                        "release": "5.module_el8.8.0+3485+7cffc4a3",
                        "repositories": [
                            {"arch": "x86_64", "name": "almalinux-8-appstream"}
                        ],
                        "version": "1.24.0",
                    },
                    {
                        "arch": "x86_64",
                        "epoch": 0,
                        "name": "nbdkit-xz-filter-debuginfo",
                        "release": "5.module_el8.8.0+3485+7cffc4a3",
                        "repositories": [
                            {
                                "arch": "x86_64",
                                "name": "almalinux-8-appstream-debuginfo",
                            }
                        ],
                        "version": "1.24.0",
                    },
                ],
                "sourcerpm": {
                    "epoch": 0,
                    "name": "nbdkit",
                    "release": "5.module_el8.8.0+3485+7cffc4a3",
                    "version": "1.24.0",
                },
            },
            {
                "packages": [
                    {
                        "arch": "src",
                        "epoch": 0,
                        "name": "netcf",
                        "release": "12.module_el8.6.0+2880+7d9e3703",
                        "repositories": [
                            {"arch": "src", "name": "almalinux-8-appstream"}
                        ],
                        "version": "0.2.8",
                    },
                    {
                        "arch": "x86_64",
                        "epoch": 0,
                        "name": "netcf",
                        "release": "12.module_el8.6.0+2880+7d9e3703",
                        "repositories": [
                            {"arch": "x86_64", "name": "almalinux-8-appstream"}
                        ],
                        "version": "0.2.8",
                    },
                    {
                        "arch": "x86_64",
                        "epoch": 0,
                        "name": "netcf-debuginfo",
                        "release": "12.module_el8.6.0+2880+7d9e3703",
                        "repositories": [
                            {
                                "arch": "x86_64",
                                "name": "almalinux-8-appstream-debuginfo",
                            }
                        ],
                        "version": "0.2.8",
                    },
                    {
                        "arch": "x86_64",
                        "epoch": 0,
                        "name": "netcf-debugsource",
                        "release": "12.module_el8.6.0+2880+7d9e3703",
                        "repositories": [
                            {
                                "arch": "x86_64",
                                "name": "almalinux-8-appstream-debuginfo",
                            }
                        ],
                        "version": "0.2.8",
                    },
                    {
                        "arch": "x86_64",
                        "epoch": 0,
                        "name": "netcf-devel",
                        "release": "12.module_el8.6.0+2880+7d9e3703",
                        "repositories": [
                            {"arch": "x86_64", "name": "almalinux-8-appstream"}
                        ],
                        "version": "0.2.8",
                    },
                    {
                        "arch": "x86_64",
                        "epoch": 0,
                        "name": "netcf-libs",
                        "release": "12.module_el8.6.0+2880+7d9e3703",
                        "repositories": [
                            {"arch": "x86_64", "name": "almalinux-8-appstream"}
                        ],
                        "version": "0.2.8",
                    },
                    {
                        "arch": "x86_64",
                        "epoch": 0,
                        "name": "netcf-libs-debuginfo",
                        "release": "12.module_el8.6.0+2880+7d9e3703",
                        "repositories": [
                            {
                                "arch": "x86_64",
                                "name": "almalinux-8-appstream-debuginfo",
                            }
                        ],
                        "version": "0.2.8",
                    },
                ],
                "sourcerpm": {
                    "epoch": 0,
                    "name": "netcf",
                    "release": "12.module_el8.6.0+2880+7d9e3703",
                    "version": "0.2.8",
                },
            },
            {
                "packages": [
                    {
                        "arch": "src",
                        "epoch": 0,
                        "name": "perl-Sys-Virt",
                        "release": "1.module_el8.6.0+2880+7d9e3703",
                        "repositories": [
                            {"arch": "src", "name": "almalinux-8-appstream"}
                        ],
                        "version": "8.0.0",
                    },
                    {
                        "arch": "x86_64",
                        "epoch": 0,
                        "name": "perl-Sys-Virt",
                        "release": "1.module_el8.6.0+2880+7d9e3703",
                        "repositories": [
                            {"arch": "x86_64", "name": "almalinux-8-appstream"}
                        ],
                        "version": "8.0.0",
                    },
                    {
                        "arch": "x86_64",
                        "epoch": 0,
                        "name": "perl-Sys-Virt-debuginfo",
                        "release": "1.module_el8.6.0+2880+7d9e3703",
                        "repositories": [
                            {
                                "arch": "x86_64",
                                "name": "almalinux-8-appstream-debuginfo",
                            }
                        ],
                        "version": "8.0.0",
                    },
                    {
                        "arch": "x86_64",
                        "epoch": 0,
                        "name": "perl-Sys-Virt-debugsource",
                        "release": "1.module_el8.6.0+2880+7d9e3703",
                        "repositories": [
                            {
                                "arch": "x86_64",
                                "name": "almalinux-8-appstream-debuginfo",
                            }
                        ],
                        "version": "8.0.0",
                    },
                ],
                "sourcerpm": {
                    "epoch": 0,
                    "name": "perl-Sys-Virt",
                    "release": "1.module_el8.6.0+2880+7d9e3703",
                    "version": "8.0.0",
                },
            },
            {
                "packages": [
                    {
                        "arch": "x86_64",
                        "epoch": 15,
                        "name": "qemu-guest-agent",
                        "release": "32.module_el8.8.0+3553+bd08596b",
                        "repositories": [
                            {"arch": "x86_64", "name": "almalinux-8-appstream"}
                        ],
                        "version": "6.2.0",
                    },
                    {
                        "arch": "x86_64",
                        "epoch": 15,
                        "name": "qemu-guest-agent-debuginfo",
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
                        "name": "qemu-img",
                        "release": "32.module_el8.8.0+3553+bd08596b",
                        "repositories": [
                            {"arch": "x86_64", "name": "almalinux-8-appstream"}
                        ],
                        "version": "6.2.0",
                    },
                    {
                        "arch": "x86_64",
                        "epoch": 15,
                        "name": "qemu-img-debuginfo",
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
                        "name": "qemu-kvm-block-curl",
                        "release": "32.module_el8.8.0+3553+bd08596b",
                        "repositories": [
                            {"arch": "x86_64", "name": "almalinux-8-appstream"}
                        ],
                        "version": "6.2.0",
                    },
                    {
                        "arch": "x86_64",
                        "epoch": 15,
                        "name": "qemu-kvm-block-curl-debuginfo",
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
                        "name": "qemu-kvm-block-gluster",
                        "release": "32.module_el8.8.0+3553+bd08596b",
                        "repositories": [
                            {"arch": "x86_64", "name": "almalinux-8-appstream"}
                        ],
                        "version": "6.2.0",
                    },
                    {
                        "arch": "x86_64",
                        "epoch": 15,
                        "name": "qemu-kvm-block-gluster-debuginfo",
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
                        "name": "qemu-kvm-block-iscsi",
                        "release": "32.module_el8.8.0+3553+bd08596b",
                        "repositories": [
                            {"arch": "x86_64", "name": "almalinux-8-appstream"}
                        ],
                        "version": "6.2.0",
                    },
                    {
                        "arch": "x86_64",
                        "epoch": 15,
                        "name": "qemu-kvm-block-iscsi-debuginfo",
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
                        "name": "qemu-kvm-block-rbd",
                        "release": "32.module_el8.8.0+3553+bd08596b",
                        "repositories": [
                            {"arch": "x86_64", "name": "almalinux-8-appstream"}
                        ],
                        "version": "6.2.0",
                    },
                    {
                        "arch": "x86_64",
                        "epoch": 15,
                        "name": "qemu-kvm-block-rbd-debuginfo",
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
                        "name": "qemu-kvm-block-ssh",
                        "release": "32.module_el8.8.0+3553+bd08596b",
                        "repositories": [
                            {"arch": "x86_64", "name": "almalinux-8-appstream"}
                        ],
                        "version": "6.2.0",
                    },
                    {
                        "arch": "x86_64",
                        "epoch": 15,
                        "name": "qemu-kvm-block-ssh-debuginfo",
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
                        "name": "qemu-kvm-common",
                        "release": "32.module_el8.8.0+3553+bd08596b",
                        "repositories": [
                            {"arch": "x86_64", "name": "almalinux-8-appstream"}
                        ],
                        "version": "6.2.0",
                    },
                    {
                        "arch": "x86_64",
                        "epoch": 15,
                        "name": "qemu-kvm-common-debuginfo",
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
                        "name": "qemu-kvm-core",
                        "release": "32.module_el8.8.0+3553+bd08596b",
                        "repositories": [
                            {"arch": "x86_64", "name": "almalinux-8-appstream"}
                        ],
                        "version": "6.2.0",
                    },
                    {
                        "arch": "x86_64",
                        "epoch": 15,
                        "name": "qemu-kvm-core-debuginfo",
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
                    {
                        "arch": "x86_64",
                        "epoch": 15,
                        "name": "qemu-kvm-docs",
                        "release": "32.module_el8.8.0+3553+bd08596b",
                        "repositories": [
                            {"arch": "x86_64", "name": "almalinux-8-appstream"}
                        ],
                        "version": "6.2.0",
                    },
                    {
                        "arch": "x86_64",
                        "epoch": 15,
                        "name": "qemu-kvm-hw-usbredir",
                        "release": "32.module_el8.8.0+3553+bd08596b",
                        "repositories": [
                            {"arch": "x86_64", "name": "almalinux-8-appstream"}
                        ],
                        "version": "6.2.0",
                    },
                    {
                        "arch": "x86_64",
                        "epoch": 15,
                        "name": "qemu-kvm-hw-usbredir-debuginfo",
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
                        "name": "qemu-kvm-ui-opengl",
                        "release": "32.module_el8.8.0+3553+bd08596b",
                        "repositories": [
                            {"arch": "x86_64", "name": "almalinux-8-appstream"}
                        ],
                        "version": "6.2.0",
                    },
                    {
                        "arch": "x86_64",
                        "epoch": 15,
                        "name": "qemu-kvm-ui-opengl-debuginfo",
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
                        "name": "qemu-kvm-ui-spice",
                        "release": "32.module_el8.8.0+3553+bd08596b",
                        "repositories": [
                            {"arch": "x86_64", "name": "almalinux-8-appstream"}
                        ],
                        "version": "6.2.0",
                    },
                    {
                        "arch": "x86_64",
                        "epoch": 15,
                        "name": "qemu-kvm-ui-spice-debuginfo",
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
            {
                "packages": [
                    {
                        "arch": "src",
                        "epoch": 0,
                        "name": "seabios",
                        "release": "3.module_el8.7.0+3346+68867adb",
                        "repositories": [
                            {"arch": "src", "name": "almalinux-8-appstream"}
                        ],
                        "version": "1.16.0",
                    },
                    {
                        "arch": "x86_64",
                        "epoch": 0,
                        "name": "seabios",
                        "release": "3.module_el8.7.0+3346+68867adb",
                        "repositories": [
                            {"arch": "x86_64", "name": "almalinux-8-appstream"}
                        ],
                        "version": "1.16.0",
                    },
                    {
                        "arch": "noarch",
                        "epoch": 0,
                        "name": "seabios-bin",
                        "release": "3.module_el8.7.0+3346+68867adb",
                        "repositories": [
                            {"arch": "x86_64", "name": "almalinux-8-appstream"}
                        ],
                        "version": "1.16.0",
                    },
                    {
                        "arch": "noarch",
                        "epoch": 0,
                        "name": "seavgabios-bin",
                        "release": "3.module_el8.7.0+3346+68867adb",
                        "repositories": [
                            {"arch": "x86_64", "name": "almalinux-8-appstream"}
                        ],
                        "version": "1.16.0",
                    },
                ],
                "sourcerpm": {
                    "epoch": 0,
                    "name": "seabios",
                    "release": "3.module_el8.7.0+3346+68867adb",
                    "version": "1.16.0",
                },
            },
            {
                "packages": [
                    {
                        "arch": "src",
                        "epoch": 1,
                        "name": "sgabios",
                        "release": "3.module_el8.6.0+2880+7d9e3703",
                        "repositories": [
                            {"arch": "src", "name": "almalinux-8-appstream"}
                        ],
                        "version": "0.20170427git",
                    },
                    {
                        "arch": "x86_64",
                        "epoch": 1,
                        "name": "sgabios",
                        "release": "3.module_el8.6.0+2880+7d9e3703",
                        "repositories": [
                            {"arch": "x86_64", "name": "almalinux-8-appstream"}
                        ],
                        "version": "0.20170427git",
                    },
                    {
                        "arch": "noarch",
                        "epoch": 1,
                        "name": "sgabios-bin",
                        "release": "3.module_el8.6.0+2880+7d9e3703",
                        "repositories": [
                            {"arch": "x86_64", "name": "almalinux-8-appstream"}
                        ],
                        "version": "0.20170427git",
                    },
                ],
                "sourcerpm": {
                    "epoch": 1,
                    "name": "sgabios",
                    "release": "3.module_el8.6.0+2880+7d9e3703",
                    "version": "0.20170427git",
                },
            },
            {
                "packages": [
                    {
                        "arch": "src",
                        "epoch": 0,
                        "name": "supermin",
                        "release": "2.module_el8.7.0+3346+68867adb",
                        "repositories": [
                            {"arch": "src", "name": "almalinux-8-appstream"}
                        ],
                        "version": "5.2.1",
                    },
                    {
                        "arch": "x86_64",
                        "epoch": 0,
                        "name": "supermin",
                        "release": "2.module_el8.7.0+3346+68867adb",
                        "repositories": [
                            {"arch": "x86_64", "name": "almalinux-8-appstream"}
                        ],
                        "version": "5.2.1",
                    },
                    {
                        "arch": "x86_64",
                        "epoch": 0,
                        "name": "supermin-debuginfo",
                        "release": "2.module_el8.7.0+3346+68867adb",
                        "repositories": [
                            {
                                "arch": "x86_64",
                                "name": "almalinux-8-appstream-debuginfo",
                            }
                        ],
                        "version": "5.2.1",
                    },
                    {
                        "arch": "x86_64",
                        "epoch": 0,
                        "name": "supermin-debugsource",
                        "release": "2.module_el8.7.0+3346+68867adb",
                        "repositories": [
                            {
                                "arch": "x86_64",
                                "name": "almalinux-8-appstream-debuginfo",
                            }
                        ],
                        "version": "5.2.1",
                    },
                    {
                        "arch": "x86_64",
                        "epoch": 0,
                        "name": "supermin-devel",
                        "release": "2.module_el8.7.0+3346+68867adb",
                        "repositories": [
                            {"arch": "x86_64", "name": "almalinux-8-appstream"}
                        ],
                        "version": "5.2.1",
                    },
                ],
                "sourcerpm": {
                    "epoch": 0,
                    "name": "supermin",
                    "release": "2.module_el8.7.0+3346+68867adb",
                    "version": "5.2.1",
                },
            },
            {
                "packages": [
                    {
                        "arch": "src",
                        "epoch": 0,
                        "name": "swtpm",
                        "release": "4.20211109gitb79fd91.module_el8.7.0+3346+68867adb",
                        "repositories": [
                            {"arch": "src", "name": "almalinux-8-appstream"}
                        ],
                        "version": "0.7.0",
                    },
                    {
                        "arch": "x86_64",
                        "epoch": 0,
                        "name": "swtpm",
                        "release": "4.20211109gitb79fd91.module_el8.7.0+3346+68867adb",
                        "repositories": [
                            {"arch": "x86_64", "name": "almalinux-8-appstream"}
                        ],
                        "version": "0.7.0",
                    },
                    {
                        "arch": "x86_64",
                        "epoch": 0,
                        "name": "swtpm-debuginfo",
                        "release": "4.20211109gitb79fd91.module_el8.7.0+3346+68867adb",
                        "repositories": [
                            {
                                "arch": "x86_64",
                                "name": "almalinux-8-appstream-debuginfo",
                            }
                        ],
                        "version": "0.7.0",
                    },
                    {
                        "arch": "x86_64",
                        "epoch": 0,
                        "name": "swtpm-debugsource",
                        "release": "4.20211109gitb79fd91.module_el8.7.0+3346+68867adb",
                        "repositories": [
                            {
                                "arch": "x86_64",
                                "name": "almalinux-8-appstream-debuginfo",
                            }
                        ],
                        "version": "0.7.0",
                    },
                    {
                        "arch": "x86_64",
                        "epoch": 0,
                        "name": "swtpm-devel",
                        "release": "4.20211109gitb79fd91.module_el8.7.0+3346+68867adb",
                        "repositories": [
                            {"arch": "x86_64", "name": "almalinux-8-appstream"}
                        ],
                        "version": "0.7.0",
                    },
                    {
                        "arch": "x86_64",
                        "epoch": 0,
                        "name": "swtpm-libs",
                        "release": "4.20211109gitb79fd91.module_el8.7.0+3346+68867adb",
                        "repositories": [
                            {"arch": "x86_64", "name": "almalinux-8-appstream"}
                        ],
                        "version": "0.7.0",
                    },
                    {
                        "arch": "x86_64",
                        "epoch": 0,
                        "name": "swtpm-libs-debuginfo",
                        "release": "4.20211109gitb79fd91.module_el8.7.0+3346+68867adb",
                        "repositories": [
                            {
                                "arch": "x86_64",
                                "name": "almalinux-8-appstream-debuginfo",
                            }
                        ],
                        "version": "0.7.0",
                    },
                    {
                        "arch": "x86_64",
                        "epoch": 0,
                        "name": "swtpm-tools",
                        "release": "4.20211109gitb79fd91.module_el8.7.0+3346+68867adb",
                        "repositories": [
                            {"arch": "x86_64", "name": "almalinux-8-appstream"}
                        ],
                        "version": "0.7.0",
                    },
                    {
                        "arch": "x86_64",
                        "epoch": 0,
                        "name": "swtpm-tools-debuginfo",
                        "release": "4.20211109gitb79fd91.module_el8.7.0+3346+68867adb",
                        "repositories": [
                            {
                                "arch": "x86_64",
                                "name": "almalinux-8-appstream-debuginfo",
                            }
                        ],
                        "version": "0.7.0",
                    },
                    {
                        "arch": "x86_64",
                        "epoch": 0,
                        "name": "swtpm-tools-pkcs11",
                        "release": "4.20211109gitb79fd91.module_el8.7.0+3346+68867adb",
                        "repositories": [
                            {"arch": "x86_64", "name": "almalinux-8-appstream"}
                        ],
                        "version": "0.7.0",
                    },
                ],
                "sourcerpm": {
                    "epoch": 0,
                    "name": "swtpm",
                    "release": "4.20211109gitb79fd91.module_el8.7.0+3346+68867adb",
                    "version": "0.7.0",
                },
            },
            {
                "packages": [
                    {
                        "arch": "src",
                        "epoch": 1,
                        "name": "virt-v2v",
                        "release": "22.module_el8.8.0+3553+bd08596b",
                        "repositories": [
                            {"arch": "src", "name": "almalinux-8-appstream"}
                        ],
                        "version": "1.42.0",
                    },
                    {
                        "arch": "x86_64",
                        "epoch": 1,
                        "name": "virt-v2v",
                        "release": "22.module_el8.8.0+3553+bd08596b",
                        "repositories": [
                            {"arch": "x86_64", "name": "almalinux-8-appstream"}
                        ],
                        "version": "1.42.0",
                    },
                    {
                        "arch": "noarch",
                        "epoch": 1,
                        "name": "virt-v2v-bash-completion",
                        "release": "22.module_el8.8.0+3553+bd08596b",
                        "repositories": [
                            {"arch": "x86_64", "name": "almalinux-8-appstream"}
                        ],
                        "version": "1.42.0",
                    },
                    {
                        "arch": "x86_64",
                        "epoch": 1,
                        "name": "virt-v2v-debuginfo",
                        "release": "22.module_el8.8.0+3553+bd08596b",
                        "repositories": [
                            {
                                "arch": "x86_64",
                                "name": "almalinux-8-appstream-debuginfo",
                            }
                        ],
                        "version": "1.42.0",
                    },
                    {
                        "arch": "x86_64",
                        "epoch": 1,
                        "name": "virt-v2v-debugsource",
                        "release": "22.module_el8.8.0+3553+bd08596b",
                        "repositories": [
                            {
                                "arch": "x86_64",
                                "name": "almalinux-8-appstream-debuginfo",
                            }
                        ],
                        "version": "1.42.0",
                    },
                    {
                        "arch": "noarch",
                        "epoch": 1,
                        "name": "virt-v2v-man-pages-ja",
                        "release": "22.module_el8.8.0+3553+bd08596b",
                        "repositories": [
                            {"arch": "x86_64", "name": "almalinux-8-appstream"}
                        ],
                        "version": "1.42.0",
                    },
                    {
                        "arch": "noarch",
                        "epoch": 1,
                        "name": "virt-v2v-man-pages-uk",
                        "release": "22.module_el8.8.0+3553+bd08596b",
                        "repositories": [
                            {"arch": "x86_64", "name": "almalinux-8-appstream"}
                        ],
                        "version": "1.42.0",
                    },
                ],
                "sourcerpm": {
                    "epoch": 1,
                    "name": "virt-v2v",
                    "release": "22.module_el8.8.0+3553+bd08596b",
                    "version": "1.42.0",
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
                "buildorder": 4,
                "name": "libguestfs",
                "ref": "61243f50c78c87d92728017318f2c1ff16d02635",
            },
            {
                "arches": ["aarch64", "i686", "ppc64le", "s390x", "x86_64"],
                "buildorder": 5,
                "name": "libguestfs-winsupport",
                "ref": "3ea195ba2c089522b83479738a54b7e879d3eb79",
            },
            {
                "arches": ["aarch64", "i686", "ppc64le", "s390x", "x86_64"],
                "buildorder": 1,
                "name": "libiscsi",
                "ref": "03c364210208727e90e1fa6b1fdf2cb8a5040991",
            },
            {
                "arches": ["aarch64", "i686", "ppc64le", "s390x", "x86_64"],
                "buildorder": 1,
                "name": "libnbd",
                "ref": "951092b53e6ed1bc9eed1b29df803595d91a2c7f",
            },
            {
                "arches": ["aarch64", "i686", "ppc64le", "s390x", "x86_64"],
                "buildorder": 1,
                "name": "libtpms",
                "ref": "86b8f6f47dc6b39d2484bb5a506f088dab36eee2",
            },
            {
                "arches": ["aarch64", "i686", "ppc64le", "s390x", "x86_64"],
                "buildorder": 3,
                "name": "libvirt",
                "ref": "722e8085db76a4334d6eac2a4668ce0a24bb6bbd",
            },
            {
                "arches": ["aarch64", "i686", "ppc64le", "s390x", "x86_64"],
                "buildorder": 4,
                "name": "libvirt-dbus",
                "ref": "4a1caa1b08966a6cfcf4860c12bf61ec54cd74d3",
            },
            {
                "arches": ["aarch64", "i686", "ppc64le", "s390x", "x86_64"],
                "buildorder": 4,
                "name": "libvirt-python",
                "ref": "062f06a46bae3b6b75fdf86cdec07eed6845f85f",
            },
            {
                "arches": ["aarch64", "i686", "ppc64le", "s390x", "x86_64"],
                "buildorder": 5,
                "name": "nbdkit",
                "ref": "317a0878c7849f4eabe3965a83734d3f5ba8ee41",
            },
            {
                "arches": ["aarch64", "i686", "ppc64le", "s390x", "x86_64"],
                "buildorder": 1,
                "name": "netcf",
                "ref": "9cafbecc76f1f51c6349c46cc0765e6c6ea9997f",
            },
            {
                "arches": ["aarch64", "i686", "ppc64le", "s390x", "x86_64"],
                "buildorder": 4,
                "name": "perl-Sys-Virt",
                "ref": "7e16e8f82d470412e6d8fe58daed83c1470d599e",
            },
            {
                "arches": ["aarch64", "i686", "ppc64le", "s390x", "x86_64"],
                "buildorder": 2,
                "name": "qemu-kvm",
                "ref": "9cf15efa745c2df3f2968d58da9ed67b29b1300f",
            },
            {
                "arches": ["aarch64", "i686", "ppc64le", "s390x", "x86_64"],
                "buildorder": 1,
                "name": "seabios",
                "ref": "94f4f45b8837c5e834b0ae11d368978c621c6fbc",
            },
            {
                "arches": ["aarch64", "i686", "ppc64le", "s390x", "x86_64"],
                "buildorder": 1,
                "name": "sgabios",
                "ref": "643ad1528f18937fa5fa0a021a8f25dd1e252596",
            },
            {
                "arches": ["aarch64", "i686", "ppc64le", "s390x", "x86_64"],
                "buildorder": 2,
                "name": "supermin",
                "ref": "502fabee05eb11c69d2fe29becf23e0e013a1995",
            },
            {
                "arches": ["aarch64", "i686", "ppc64le", "s390x", "x86_64"],
                "buildorder": 2,
                "name": "swtpm",
                "ref": "12e26459a3feb201950bf8d52a9af95afd601a5b",
            },
            {
                "arches": ["aarch64", "i686", "ppc64le", "s390x", "x86_64"],
                "buildorder": 6,
                "name": "virt-v2v",
                "ref": "22c887f059f0127d58f53e1d00b38c297e565890",
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
                    {
                        "arch": "i686",
                        "epoch": 0,
                        "name": "perl-hivex",
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
                        "name": "perl-hivex-debuginfo",
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
                        "name": "python3-hivex",
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
                        "name": "python3-hivex-debuginfo",
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
                        "name": "ruby-hivex",
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
                        "name": "ruby-hivex-debuginfo",
                        "release": "23.module_el8.6.0+2880+7d9e3703",
                        "repositories": [
                            {
                                "arch": "x86_64",
                                "name": "almalinux-8-powertools-debuginfo",
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
            {
                "packages": [
                    {
                        "arch": "i686",
                        "epoch": 0,
                        "name": "libguestfs-winsupport",
                        "release": "1.module_el8.8.0+3485+7cffc4a3",
                        "repositories": [
                            {
                                "arch": "x86_64",
                                "name": "almalinux-8-powertools",
                            }
                        ],
                        "version": "8.8",
                    }
                ],
                "sourcerpm": {
                    "epoch": 0,
                    "name": "libguestfs-winsupport",
                    "release": "1.module_el8.8.0+3485+7cffc4a3",
                    "version": "8.8",
                },
            },
            {
                "packages": [
                    {
                        "arch": "i686",
                        "epoch": 0,
                        "name": "libiscsi",
                        "release": "8.module_el8.6.0+2880+7d9e3703",
                        "repositories": [
                            {
                                "arch": "x86_64",
                                "name": "almalinux-8-powertools",
                            }
                        ],
                        "version": "1.18.0",
                    },
                    {
                        "arch": "i686",
                        "epoch": 0,
                        "name": "libiscsi-debuginfo",
                        "release": "8.module_el8.6.0+2880+7d9e3703",
                        "repositories": [
                            {
                                "arch": "x86_64",
                                "name": "almalinux-8-powertools-debuginfo",
                            }
                        ],
                        "version": "1.18.0",
                    },
                    {
                        "arch": "i686",
                        "epoch": 0,
                        "name": "libiscsi-debugsource",
                        "release": "8.module_el8.6.0+2880+7d9e3703",
                        "repositories": [
                            {
                                "arch": "x86_64",
                                "name": "almalinux-8-powertools-debuginfo",
                            }
                        ],
                        "version": "1.18.0",
                    },
                    {
                        "arch": "i686",
                        "epoch": 0,
                        "name": "libiscsi-devel",
                        "release": "8.module_el8.6.0+2880+7d9e3703",
                        "repositories": [
                            {
                                "arch": "x86_64",
                                "name": "almalinux-8-powertools",
                            }
                        ],
                        "version": "1.18.0",
                    },
                    {
                        "arch": "i686",
                        "epoch": 0,
                        "name": "libiscsi-utils",
                        "release": "8.module_el8.6.0+2880+7d9e3703",
                        "repositories": [
                            {
                                "arch": "x86_64",
                                "name": "almalinux-8-powertools",
                            }
                        ],
                        "version": "1.18.0",
                    },
                    {
                        "arch": "i686",
                        "epoch": 0,
                        "name": "libiscsi-utils-debuginfo",
                        "release": "8.module_el8.6.0+2880+7d9e3703",
                        "repositories": [
                            {
                                "arch": "x86_64",
                                "name": "almalinux-8-powertools-debuginfo",
                            }
                        ],
                        "version": "1.18.0",
                    },
                ],
                "sourcerpm": {
                    "epoch": 0,
                    "name": "libiscsi",
                    "release": "8.module_el8.6.0+2880+7d9e3703",
                    "version": "1.18.0",
                },
            },
            {
                "packages": [
                    {
                        "arch": "i686",
                        "epoch": 0,
                        "name": "libnbd",
                        "release": "5.module_el8.6.0+2880+7d9e3703",
                        "repositories": [
                            {
                                "arch": "x86_64",
                                "name": "almalinux-8-powertools",
                            }
                        ],
                        "version": "1.6.0",
                    },
                    {
                        "arch": "i686",
                        "epoch": 0,
                        "name": "libnbd-debuginfo",
                        "release": "5.module_el8.6.0+2880+7d9e3703",
                        "repositories": [
                            {
                                "arch": "x86_64",
                                "name": "almalinux-8-powertools-debuginfo",
                            }
                        ],
                        "version": "1.6.0",
                    },
                    {
                        "arch": "i686",
                        "epoch": 0,
                        "name": "libnbd-debugsource",
                        "release": "5.module_el8.6.0+2880+7d9e3703",
                        "repositories": [
                            {
                                "arch": "x86_64",
                                "name": "almalinux-8-powertools-debuginfo",
                            }
                        ],
                        "version": "1.6.0",
                    },
                    {
                        "arch": "i686",
                        "epoch": 0,
                        "name": "libnbd-devel",
                        "release": "5.module_el8.6.0+2880+7d9e3703",
                        "repositories": [
                            {
                                "arch": "x86_64",
                                "name": "almalinux-8-powertools",
                            }
                        ],
                        "version": "1.6.0",
                    },
                    {
                        "arch": "i686",
                        "epoch": 0,
                        "name": "nbdfuse",
                        "release": "5.module_el8.6.0+2880+7d9e3703",
                        "repositories": [
                            {
                                "arch": "x86_64",
                                "name": "almalinux-8-powertools",
                            }
                        ],
                        "version": "1.6.0",
                    },
                    {
                        "arch": "i686",
                        "epoch": 0,
                        "name": "nbdfuse-debuginfo",
                        "release": "5.module_el8.6.0+2880+7d9e3703",
                        "repositories": [
                            {
                                "arch": "x86_64",
                                "name": "almalinux-8-powertools-debuginfo",
                            }
                        ],
                        "version": "1.6.0",
                    },
                    {
                        "arch": "i686",
                        "epoch": 0,
                        "name": "ocaml-libnbd",
                        "release": "5.module_el8.6.0+2880+7d9e3703",
                        "repositories": [
                            {
                                "arch": "x86_64",
                                "name": "almalinux-8-powertools",
                            }
                        ],
                        "version": "1.6.0",
                    },
                    {
                        "arch": "x86_64",
                        "epoch": 0,
                        "name": "ocaml-libnbd",
                        "release": "5.module_el8.6.0+2880+7d9e3703",
                        "repositories": [
                            {
                                "arch": "x86_64",
                                "name": "almalinux-8-powertools",
                            }
                        ],
                        "version": "1.6.0",
                    },
                    {
                        "arch": "i686",
                        "epoch": 0,
                        "name": "ocaml-libnbd-debuginfo",
                        "release": "5.module_el8.6.0+2880+7d9e3703",
                        "repositories": [
                            {
                                "arch": "x86_64",
                                "name": "almalinux-8-powertools-debuginfo",
                            }
                        ],
                        "version": "1.6.0",
                    },
                    {
                        "arch": "x86_64",
                        "epoch": 0,
                        "name": "ocaml-libnbd-debuginfo",
                        "release": "5.module_el8.6.0+2880+7d9e3703",
                        "repositories": [
                            {
                                "arch": "x86_64",
                                "name": "almalinux-8-powertools-debuginfo",
                            }
                        ],
                        "version": "1.6.0",
                    },
                    {
                        "arch": "i686",
                        "epoch": 0,
                        "name": "ocaml-libnbd-devel",
                        "release": "5.module_el8.6.0+2880+7d9e3703",
                        "repositories": [
                            {
                                "arch": "x86_64",
                                "name": "almalinux-8-powertools",
                            }
                        ],
                        "version": "1.6.0",
                    },
                    {
                        "arch": "x86_64",
                        "epoch": 0,
                        "name": "ocaml-libnbd-devel",
                        "release": "5.module_el8.6.0+2880+7d9e3703",
                        "repositories": [
                            {
                                "arch": "x86_64",
                                "name": "almalinux-8-powertools",
                            }
                        ],
                        "version": "1.6.0",
                    },
                    {
                        "arch": "i686",
                        "epoch": 0,
                        "name": "python3-libnbd",
                        "release": "5.module_el8.6.0+2880+7d9e3703",
                        "repositories": [
                            {
                                "arch": "x86_64",
                                "name": "almalinux-8-powertools",
                            }
                        ],
                        "version": "1.6.0",
                    },
                    {
                        "arch": "i686",
                        "epoch": 0,
                        "name": "python3-libnbd-debuginfo",
                        "release": "5.module_el8.6.0+2880+7d9e3703",
                        "repositories": [
                            {
                                "arch": "x86_64",
                                "name": "almalinux-8-powertools-debuginfo",
                            }
                        ],
                        "version": "1.6.0",
                    },
                ],
                "sourcerpm": {
                    "epoch": 0,
                    "name": "libnbd",
                    "release": "5.module_el8.6.0+2880+7d9e3703",
                    "version": "1.6.0",
                },
            },
            {
                "packages": [
                    {
                        "arch": "i686",
                        "epoch": 0,
                        "name": "libvirt",
                        "release": "19.2.module_el8.8.0+3585+76b9c397.alma",
                        "repositories": [
                            {
                                "arch": "x86_64",
                                "name": "almalinux-8-powertools",
                            }
                        ],
                        "version": "8.0.0",
                    },
                    {
                        "arch": "i686",
                        "epoch": 0,
                        "name": "libvirt-client",
                        "release": "19.2.module_el8.8.0+3585+76b9c397.alma",
                        "repositories": [
                            {
                                "arch": "x86_64",
                                "name": "almalinux-8-powertools",
                            }
                        ],
                        "version": "8.0.0",
                    },
                    {
                        "arch": "i686",
                        "epoch": 0,
                        "name": "libvirt-client-debuginfo",
                        "release": "19.2.module_el8.8.0+3585+76b9c397.alma",
                        "repositories": [
                            {
                                "arch": "x86_64",
                                "name": "almalinux-8-appstream-debuginfo",
                            }
                        ],
                        "version": "8.0.0",
                    },
                    {
                        "arch": "i686",
                        "epoch": 0,
                        "name": "libvirt-daemon",
                        "release": "19.2.module_el8.8.0+3585+76b9c397.alma",
                        "repositories": [
                            {
                                "arch": "x86_64",
                                "name": "almalinux-8-powertools",
                            }
                        ],
                        "version": "8.0.0",
                    },
                    {
                        "arch": "i686",
                        "epoch": 0,
                        "name": "libvirt-daemon-config-network",
                        "release": "19.2.module_el8.8.0+3585+76b9c397.alma",
                        "repositories": [
                            {
                                "arch": "x86_64",
                                "name": "almalinux-8-powertools",
                            }
                        ],
                        "version": "8.0.0",
                    },
                    {
                        "arch": "i686",
                        "epoch": 0,
                        "name": "libvirt-daemon-config-nwfilter",
                        "release": "19.2.module_el8.8.0+3585+76b9c397.alma",
                        "repositories": [
                            {
                                "arch": "x86_64",
                                "name": "almalinux-8-powertools",
                            }
                        ],
                        "version": "8.0.0",
                    },
                    {
                        "arch": "i686",
                        "epoch": 0,
                        "name": "libvirt-daemon-debuginfo",
                        "release": "19.2.module_el8.8.0+3585+76b9c397.alma",
                        "repositories": [
                            {
                                "arch": "x86_64",
                                "name": "almalinux-8-appstream-debuginfo",
                            }
                        ],
                        "version": "8.0.0",
                    },
                    {
                        "arch": "i686",
                        "epoch": 0,
                        "name": "libvirt-daemon-driver-interface",
                        "release": "19.2.module_el8.8.0+3585+76b9c397.alma",
                        "repositories": [
                            {
                                "arch": "x86_64",
                                "name": "almalinux-8-powertools",
                            }
                        ],
                        "version": "8.0.0",
                    },
                    {
                        "arch": "i686",
                        "epoch": 0,
                        "name": "libvirt-daemon-driver-interface-debuginfo",
                        "release": "19.2.module_el8.8.0+3585+76b9c397.alma",
                        "repositories": [
                            {
                                "arch": "x86_64",
                                "name": "almalinux-8-appstream-debuginfo",
                            }
                        ],
                        "version": "8.0.0",
                    },
                    {
                        "arch": "i686",
                        "epoch": 0,
                        "name": "libvirt-daemon-driver-network",
                        "release": "19.2.module_el8.8.0+3585+76b9c397.alma",
                        "repositories": [
                            {
                                "arch": "x86_64",
                                "name": "almalinux-8-powertools",
                            }
                        ],
                        "version": "8.0.0",
                    },
                    {
                        "arch": "i686",
                        "epoch": 0,
                        "name": "libvirt-daemon-driver-network-debuginfo",
                        "release": "19.2.module_el8.8.0+3585+76b9c397.alma",
                        "repositories": [
                            {
                                "arch": "x86_64",
                                "name": "almalinux-8-appstream-debuginfo",
                            }
                        ],
                        "version": "8.0.0",
                    },
                    {
                        "arch": "i686",
                        "epoch": 0,
                        "name": "libvirt-daemon-driver-nodedev",
                        "release": "19.2.module_el8.8.0+3585+76b9c397.alma",
                        "repositories": [
                            {
                                "arch": "x86_64",
                                "name": "almalinux-8-powertools",
                            }
                        ],
                        "version": "8.0.0",
                    },
                    {
                        "arch": "i686",
                        "epoch": 0,
                        "name": "libvirt-daemon-driver-nodedev-debuginfo",
                        "release": "19.2.module_el8.8.0+3585+76b9c397.alma",
                        "repositories": [
                            {
                                "arch": "x86_64",
                                "name": "almalinux-8-appstream-debuginfo",
                            }
                        ],
                        "version": "8.0.0",
                    },
                    {
                        "arch": "i686",
                        "epoch": 0,
                        "name": "libvirt-daemon-driver-nwfilter",
                        "release": "19.2.module_el8.8.0+3585+76b9c397.alma",
                        "repositories": [
                            {
                                "arch": "x86_64",
                                "name": "almalinux-8-powertools",
                            }
                        ],
                        "version": "8.0.0",
                    },
                    {
                        "arch": "i686",
                        "epoch": 0,
                        "name": "libvirt-daemon-driver-nwfilter-debuginfo",
                        "release": "19.2.module_el8.8.0+3585+76b9c397.alma",
                        "repositories": [
                            {
                                "arch": "x86_64",
                                "name": "almalinux-8-appstream-debuginfo",
                            }
                        ],
                        "version": "8.0.0",
                    },
                    {
                        "arch": "i686",
                        "epoch": 0,
                        "name": "libvirt-daemon-driver-secret",
                        "release": "19.2.module_el8.8.0+3585+76b9c397.alma",
                        "repositories": [
                            {
                                "arch": "x86_64",
                                "name": "almalinux-8-powertools",
                            }
                        ],
                        "version": "8.0.0",
                    },
                    {
                        "arch": "i686",
                        "epoch": 0,
                        "name": "libvirt-daemon-driver-secret-debuginfo",
                        "release": "19.2.module_el8.8.0+3585+76b9c397.alma",
                        "repositories": [
                            {
                                "arch": "x86_64",
                                "name": "almalinux-8-appstream-debuginfo",
                            }
                        ],
                        "version": "8.0.0",
                    },
                    {
                        "arch": "i686",
                        "epoch": 0,
                        "name": "libvirt-daemon-driver-storage",
                        "release": "19.2.module_el8.8.0+3585+76b9c397.alma",
                        "repositories": [
                            {
                                "arch": "x86_64",
                                "name": "almalinux-8-powertools",
                            }
                        ],
                        "version": "8.0.0",
                    },
                    {
                        "arch": "i686",
                        "epoch": 0,
                        "name": "libvirt-daemon-driver-storage-core",
                        "release": "19.2.module_el8.8.0+3585+76b9c397.alma",
                        "repositories": [
                            {
                                "arch": "x86_64",
                                "name": "almalinux-8-powertools",
                            }
                        ],
                        "version": "8.0.0",
                    },
                    {
                        "arch": "i686",
                        "epoch": 0,
                        "name": "libvirt-daemon-driver-storage-core-debuginfo",
                        "release": "19.2.module_el8.8.0+3585+76b9c397.alma",
                        "repositories": [
                            {
                                "arch": "x86_64",
                                "name": "almalinux-8-appstream-debuginfo",
                            }
                        ],
                        "version": "8.0.0",
                    },
                    {
                        "arch": "i686",
                        "epoch": 0,
                        "name": "libvirt-daemon-driver-storage-disk",
                        "release": "19.2.module_el8.8.0+3585+76b9c397.alma",
                        "repositories": [
                            {
                                "arch": "x86_64",
                                "name": "almalinux-8-powertools",
                            }
                        ],
                        "version": "8.0.0",
                    },
                    {
                        "arch": "i686",
                        "epoch": 0,
                        "name": "libvirt-daemon-driver-storage-disk-debuginfo",
                        "release": "19.2.module_el8.8.0+3585+76b9c397.alma",
                        "repositories": [
                            {
                                "arch": "x86_64",
                                "name": "almalinux-8-appstream-debuginfo",
                            }
                        ],
                        "version": "8.0.0",
                    },
                    {
                        "arch": "i686",
                        "epoch": 0,
                        "name": "libvirt-daemon-driver-storage-iscsi",
                        "release": "19.2.module_el8.8.0+3585+76b9c397.alma",
                        "repositories": [
                            {
                                "arch": "x86_64",
                                "name": "almalinux-8-powertools",
                            }
                        ],
                        "version": "8.0.0",
                    },
                    {
                        "arch": "i686",
                        "epoch": 0,
                        "name": "libvirt-daemon-driver-storage-iscsi-debuginfo",
                        "release": "19.2.module_el8.8.0+3585+76b9c397.alma",
                        "repositories": [
                            {
                                "arch": "x86_64",
                                "name": "almalinux-8-appstream-debuginfo",
                            }
                        ],
                        "version": "8.0.0",
                    },
                    {
                        "arch": "i686",
                        "epoch": 0,
                        "name": "libvirt-daemon-driver-storage-iscsi-direct",
                        "release": "19.2.module_el8.8.0+3585+76b9c397.alma",
                        "repositories": [
                            {
                                "arch": "x86_64",
                                "name": "almalinux-8-powertools",
                            }
                        ],
                        "version": "8.0.0",
                    },
                    {
                        "arch": "i686",
                        "epoch": 0,
                        "name": "libvirt-daemon-driver-storage-iscsi-direct-debuginfo",
                        "release": "19.2.module_el8.8.0+3585+76b9c397.alma",
                        "repositories": [
                            {
                                "arch": "x86_64",
                                "name": "almalinux-8-appstream-debuginfo",
                            }
                        ],
                        "version": "8.0.0",
                    },
                    {
                        "arch": "i686",
                        "epoch": 0,
                        "name": "libvirt-daemon-driver-storage-logical",
                        "release": "19.2.module_el8.8.0+3585+76b9c397.alma",
                        "repositories": [
                            {
                                "arch": "x86_64",
                                "name": "almalinux-8-powertools",
                            }
                        ],
                        "version": "8.0.0",
                    },
                    {
                        "arch": "i686",
                        "epoch": 0,
                        "name": "libvirt-daemon-driver-storage-logical-debuginfo",
                        "release": "19.2.module_el8.8.0+3585+76b9c397.alma",
                        "repositories": [
                            {
                                "arch": "x86_64",
                                "name": "almalinux-8-appstream-debuginfo",
                            }
                        ],
                        "version": "8.0.0",
                    },
                    {
                        "arch": "i686",
                        "epoch": 0,
                        "name": "libvirt-daemon-driver-storage-mpath",
                        "release": "19.2.module_el8.8.0+3585+76b9c397.alma",
                        "repositories": [
                            {
                                "arch": "x86_64",
                                "name": "almalinux-8-powertools",
                            }
                        ],
                        "version": "8.0.0",
                    },
                    {
                        "arch": "i686",
                        "epoch": 0,
                        "name": "libvirt-daemon-driver-storage-mpath-debuginfo",
                        "release": "19.2.module_el8.8.0+3585+76b9c397.alma",
                        "repositories": [
                            {
                                "arch": "x86_64",
                                "name": "almalinux-8-appstream-debuginfo",
                            }
                        ],
                        "version": "8.0.0",
                    },
                    {
                        "arch": "i686",
                        "epoch": 0,
                        "name": "libvirt-daemon-driver-storage-scsi",
                        "release": "19.2.module_el8.8.0+3585+76b9c397.alma",
                        "repositories": [
                            {
                                "arch": "x86_64",
                                "name": "almalinux-8-powertools",
                            }
                        ],
                        "version": "8.0.0",
                    },
                    {
                        "arch": "i686",
                        "epoch": 0,
                        "name": "libvirt-daemon-driver-storage-scsi-debuginfo",
                        "release": "19.2.module_el8.8.0+3585+76b9c397.alma",
                        "repositories": [
                            {
                                "arch": "x86_64",
                                "name": "almalinux-8-appstream-debuginfo",
                            }
                        ],
                        "version": "8.0.0",
                    },
                    {
                        "arch": "i686",
                        "epoch": 0,
                        "name": "libvirt-debuginfo",
                        "release": "19.2.module_el8.8.0+3585+76b9c397.alma",
                        "repositories": [
                            {
                                "arch": "x86_64",
                                "name": "almalinux-8-appstream-debuginfo",
                            }
                        ],
                        "version": "8.0.0",
                    },
                    {
                        "arch": "i686",
                        "epoch": 0,
                        "name": "libvirt-debugsource",
                        "release": "19.2.module_el8.8.0+3585+76b9c397.alma",
                        "repositories": [
                            {
                                "arch": "x86_64",
                                "name": "almalinux-8-appstream-debuginfo",
                            }
                        ],
                        "version": "8.0.0",
                    },
                    {
                        "arch": "i686",
                        "epoch": 0,
                        "name": "libvirt-devel",
                        "release": "19.2.module_el8.8.0+3585+76b9c397.alma",
                        "repositories": [
                            {
                                "arch": "x86_64",
                                "name": "almalinux-8-powertools",
                            }
                        ],
                        "version": "8.0.0",
                    },
                    {
                        "arch": "i686",
                        "epoch": 0,
                        "name": "libvirt-docs",
                        "release": "19.2.module_el8.8.0+3585+76b9c397.alma",
                        "repositories": [
                            {
                                "arch": "x86_64",
                                "name": "almalinux-8-powertools",
                            }
                        ],
                        "version": "8.0.0",
                    },
                    {
                        "arch": "i686",
                        "epoch": 0,
                        "name": "libvirt-libs",
                        "release": "19.2.module_el8.8.0+3585+76b9c397.alma",
                        "repositories": [
                            {
                                "arch": "x86_64",
                                "name": "almalinux-8-powertools",
                            }
                        ],
                        "version": "8.0.0",
                    },
                    {
                        "arch": "i686",
                        "epoch": 0,
                        "name": "libvirt-libs-debuginfo",
                        "release": "19.2.module_el8.8.0+3585+76b9c397.alma",
                        "repositories": [
                            {
                                "arch": "x86_64",
                                "name": "almalinux-8-appstream-debuginfo",
                            }
                        ],
                        "version": "8.0.0",
                    },
                    {
                        "arch": "i686",
                        "epoch": 0,
                        "name": "libvirt-nss",
                        "release": "19.2.module_el8.8.0+3585+76b9c397.alma",
                        "repositories": [
                            {
                                "arch": "x86_64",
                                "name": "almalinux-8-powertools",
                            }
                        ],
                        "version": "8.0.0",
                    },
                    {
                        "arch": "i686",
                        "epoch": 0,
                        "name": "libvirt-nss-debuginfo",
                        "release": "19.2.module_el8.8.0+3585+76b9c397.alma",
                        "repositories": [
                            {
                                "arch": "x86_64",
                                "name": "almalinux-8-appstream-debuginfo",
                            }
                        ],
                        "version": "8.0.0",
                    },
                    {
                        "arch": "i686",
                        "epoch": 0,
                        "name": "libvirt-wireshark",
                        "release": "19.2.module_el8.8.0+3585+76b9c397.alma",
                        "repositories": [
                            {
                                "arch": "x86_64",
                                "name": "almalinux-8-powertools",
                            }
                        ],
                        "version": "8.0.0",
                    },
                    {
                        "arch": "i686",
                        "epoch": 0,
                        "name": "libvirt-wireshark-debuginfo",
                        "release": "19.2.module_el8.8.0+3585+76b9c397.alma",
                        "repositories": [
                            {
                                "arch": "x86_64",
                                "name": "almalinux-8-appstream-debuginfo",
                            }
                        ],
                        "version": "8.0.0",
                    },
                ],
                "sourcerpm": {
                    "epoch": 0,
                    "name": "libvirt",
                    "release": "19.2.module_el8.8.0+3585+76b9c397.alma",
                    "version": "8.0.0",
                },
            },
            {
                "packages": [
                    {
                        "arch": "i686",
                        "epoch": 0,
                        "name": "libvirt-dbus",
                        "release": "2.module_el8.6.0+2880+7d9e3703",
                        "repositories": [
                            {
                                "arch": "x86_64",
                                "name": "almalinux-8-powertools",
                            }
                        ],
                        "version": "1.3.0",
                    },
                    {
                        "arch": "i686",
                        "epoch": 0,
                        "name": "libvirt-dbus-debuginfo",
                        "release": "2.module_el8.6.0+2880+7d9e3703",
                        "repositories": [
                            {
                                "arch": "x86_64",
                                "name": "almalinux-8-powertools-debuginfo",
                            }
                        ],
                        "version": "1.3.0",
                    },
                    {
                        "arch": "i686",
                        "epoch": 0,
                        "name": "libvirt-dbus-debugsource",
                        "release": "2.module_el8.6.0+2880+7d9e3703",
                        "repositories": [
                            {
                                "arch": "x86_64",
                                "name": "almalinux-8-powertools-debuginfo",
                            }
                        ],
                        "version": "1.3.0",
                    },
                ],
                "sourcerpm": {
                    "epoch": 0,
                    "name": "libvirt-dbus",
                    "release": "2.module_el8.6.0+2880+7d9e3703",
                    "version": "1.3.0",
                },
            },
            {
                "packages": [
                    {
                        "arch": "i686",
                        "epoch": 0,
                        "name": "libvirt-python-debugsource",
                        "release": "2.module_el8.7.0+3346+68867adb",
                        "repositories": [
                            {
                                "arch": "x86_64",
                                "name": "almalinux-8-powertools-debuginfo",
                            }
                        ],
                        "version": "8.0.0",
                    },
                    {
                        "arch": "i686",
                        "epoch": 0,
                        "name": "python3-libvirt",
                        "release": "2.module_el8.7.0+3346+68867adb",
                        "repositories": [
                            {
                                "arch": "x86_64",
                                "name": "almalinux-8-powertools",
                            }
                        ],
                        "version": "8.0.0",
                    },
                    {
                        "arch": "i686",
                        "epoch": 0,
                        "name": "python3-libvirt-debuginfo",
                        "release": "2.module_el8.7.0+3346+68867adb",
                        "repositories": [
                            {
                                "arch": "x86_64",
                                "name": "almalinux-8-powertools-debuginfo",
                            }
                        ],
                        "version": "8.0.0",
                    },
                ],
                "sourcerpm": {
                    "epoch": 0,
                    "name": "libvirt-python",
                    "release": "2.module_el8.7.0+3346+68867adb",
                    "version": "8.0.0",
                },
            },
            {
                "packages": [
                    {
                        "arch": "i686",
                        "epoch": 0,
                        "name": "netcf",
                        "release": "12.module_el8.6.0+2880+7d9e3703",
                        "repositories": [
                            {
                                "arch": "x86_64",
                                "name": "almalinux-8-powertools",
                            }
                        ],
                        "version": "0.2.8",
                    },
                    {
                        "arch": "i686",
                        "epoch": 0,
                        "name": "netcf-debuginfo",
                        "release": "12.module_el8.6.0+2880+7d9e3703",
                        "repositories": [
                            {
                                "arch": "x86_64",
                                "name": "almalinux-8-powertools-debuginfo",
                            }
                        ],
                        "version": "0.2.8",
                    },
                    {
                        "arch": "i686",
                        "epoch": 0,
                        "name": "netcf-debugsource",
                        "release": "12.module_el8.6.0+2880+7d9e3703",
                        "repositories": [
                            {
                                "arch": "x86_64",
                                "name": "almalinux-8-powertools-debuginfo",
                            }
                        ],
                        "version": "0.2.8",
                    },
                    {
                        "arch": "i686",
                        "epoch": 0,
                        "name": "netcf-devel",
                        "release": "12.module_el8.6.0+2880+7d9e3703",
                        "repositories": [
                            {
                                "arch": "x86_64",
                                "name": "almalinux-8-powertools",
                            }
                        ],
                        "version": "0.2.8",
                    },
                    {
                        "arch": "i686",
                        "epoch": 0,
                        "name": "netcf-libs",
                        "release": "12.module_el8.6.0+2880+7d9e3703",
                        "repositories": [
                            {
                                "arch": "x86_64",
                                "name": "almalinux-8-powertools",
                            }
                        ],
                        "version": "0.2.8",
                    },
                    {
                        "arch": "i686",
                        "epoch": 0,
                        "name": "netcf-libs-debuginfo",
                        "release": "12.module_el8.6.0+2880+7d9e3703",
                        "repositories": [
                            {
                                "arch": "x86_64",
                                "name": "almalinux-8-powertools-debuginfo",
                            }
                        ],
                        "version": "0.2.8",
                    },
                ],
                "sourcerpm": {
                    "epoch": 0,
                    "name": "netcf",
                    "release": "12.module_el8.6.0+2880+7d9e3703",
                    "version": "0.2.8",
                },
            },
            {
                "packages": [
                    {
                        "arch": "x86_64",
                        "epoch": 1,
                        "name": "ocaml-libguestfs",
                        "release": "9.module_el8.7.0+3493+5ed0bd1c.alma",
                        "repositories": [
                            {
                                "arch": "x86_64",
                                "name": "almalinux-8-powertools",
                            }
                        ],
                        "version": "1.44.0",
                    },
                    {
                        "arch": "x86_64",
                        "epoch": 1,
                        "name": "ocaml-libguestfs-debuginfo",
                        "release": "9.module_el8.7.0+3493+5ed0bd1c.alma",
                        "repositories": [
                            {
                                "arch": "x86_64",
                                "name": "almalinux-8-powertools-debuginfo",
                            }
                        ],
                        "version": "1.44.0",
                    },
                    {
                        "arch": "x86_64",
                        "epoch": 1,
                        "name": "ocaml-libguestfs-devel",
                        "release": "9.module_el8.7.0+3493+5ed0bd1c.alma",
                        "repositories": [
                            {
                                "arch": "x86_64",
                                "name": "almalinux-8-powertools",
                            }
                        ],
                        "version": "1.44.0",
                    },
                ],
                "sourcerpm": {
                    "epoch": 0,
                    "name": "libguestfs",
                    "release": "9.module_el8.7.0+3493+5ed0bd1c.alma",
                    "version": "1.44.0",
                },
            },
            {
                "packages": [
                    {
                        "arch": "i686",
                        "epoch": 0,
                        "name": "perl-Sys-Virt",
                        "release": "1.module_el8.6.0+2880+7d9e3703",
                        "repositories": [
                            {
                                "arch": "x86_64",
                                "name": "almalinux-8-powertools",
                            }
                        ],
                        "version": "8.0.0",
                    },
                    {
                        "arch": "i686",
                        "epoch": 0,
                        "name": "perl-Sys-Virt-debuginfo",
                        "release": "1.module_el8.6.0+2880+7d9e3703",
                        "repositories": [
                            {
                                "arch": "x86_64",
                                "name": "almalinux-8-powertools-debuginfo",
                            }
                        ],
                        "version": "8.0.0",
                    },
                    {
                        "arch": "i686",
                        "epoch": 0,
                        "name": "perl-Sys-Virt-debugsource",
                        "release": "1.module_el8.6.0+2880+7d9e3703",
                        "repositories": [
                            {
                                "arch": "x86_64",
                                "name": "almalinux-8-powertools-debuginfo",
                            }
                        ],
                        "version": "8.0.0",
                    },
                ],
                "sourcerpm": {
                    "epoch": 0,
                    "name": "perl-Sys-Virt",
                    "release": "1.module_el8.6.0+2880+7d9e3703",
                    "version": "8.0.0",
                },
            },
            {
                "packages": [
                    {
                        "arch": "x86_64",
                        "epoch": 15,
                        "name": "qemu-kvm-tests",
                        "release": "32.module_el8.8.0+3553+bd08596b",
                        "repositories": [
                            {
                                "arch": "x86_64",
                                "name": "almalinux-8-powertools",
                            }
                        ],
                        "version": "6.2.0",
                    }
                ],
                "sourcerpm": {
                    "epoch": 0,
                    "name": "qemu-kvm",
                    "release": "32.module_el8.8.0+3553+bd08596b",
                    "version": "6.2.0",
                },
            },
            {
                "packages": [
                    {
                        "arch": "i686",
                        "epoch": 1,
                        "name": "sgabios",
                        "release": "3.module_el8.6.0+2880+7d9e3703",
                        "repositories": [
                            {
                                "arch": "x86_64",
                                "name": "almalinux-8-powertools",
                            }
                        ],
                        "version": "0.20170427git",
                    }
                ],
                "sourcerpm": {
                    "epoch": 0,
                    "name": "sgabios",
                    "release": "3.module_el8.6.0+2880+7d9e3703",
                    "version": "0.20170427git",
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
                "buildorder": 4,
                "name": "libguestfs",
                "ref": "61243f50c78c87d92728017318f2c1ff16d02635",
            },
            {
                "arches": ["aarch64", "i686", "ppc64le", "s390x", "x86_64"],
                "buildorder": 5,
                "name": "libguestfs-winsupport",
                "ref": "3ea195ba2c089522b83479738a54b7e879d3eb79",
            },
            {
                "arches": ["aarch64", "i686", "ppc64le", "s390x", "x86_64"],
                "buildorder": 1,
                "name": "libiscsi",
                "ref": "03c364210208727e90e1fa6b1fdf2cb8a5040991",
            },
            {
                "arches": ["aarch64", "i686", "ppc64le", "s390x", "x86_64"],
                "buildorder": 1,
                "name": "libnbd",
                "ref": "951092b53e6ed1bc9eed1b29df803595d91a2c7f",
            },
            {
                "arches": ["aarch64", "i686", "ppc64le", "s390x", "x86_64"],
                "buildorder": 1,
                "name": "libtpms",
                "ref": "86b8f6f47dc6b39d2484bb5a506f088dab36eee2",
            },
            {
                "arches": ["aarch64", "i686", "ppc64le", "s390x", "x86_64"],
                "buildorder": 3,
                "name": "libvirt",
                "ref": "722e8085db76a4334d6eac2a4668ce0a24bb6bbd",
            },
            {
                "arches": ["aarch64", "i686", "ppc64le", "s390x", "x86_64"],
                "buildorder": 4,
                "name": "libvirt-dbus",
                "ref": "4a1caa1b08966a6cfcf4860c12bf61ec54cd74d3",
            },
            {
                "arches": ["aarch64", "i686", "ppc64le", "s390x", "x86_64"],
                "buildorder": 4,
                "name": "libvirt-python",
                "ref": "062f06a46bae3b6b75fdf86cdec07eed6845f85f",
            },
            {
                "arches": ["aarch64", "i686", "ppc64le", "s390x", "x86_64"],
                "buildorder": 5,
                "name": "nbdkit",
                "ref": "317a0878c7849f4eabe3965a83734d3f5ba8ee41",
            },
            {
                "arches": ["aarch64", "i686", "ppc64le", "s390x", "x86_64"],
                "buildorder": 1,
                "name": "netcf",
                "ref": "9cafbecc76f1f51c6349c46cc0765e6c6ea9997f",
            },
            {
                "arches": ["aarch64", "i686", "ppc64le", "s390x", "x86_64"],
                "buildorder": 4,
                "name": "perl-Sys-Virt",
                "ref": "7e16e8f82d470412e6d8fe58daed83c1470d599e",
            },
            {
                "arches": ["aarch64", "i686", "ppc64le", "s390x", "x86_64"],
                "buildorder": 2,
                "name": "qemu-kvm",
                "ref": "9cf15efa745c2df3f2968d58da9ed67b29b1300f",
            },
            {
                "arches": ["aarch64", "i686", "ppc64le", "s390x", "x86_64"],
                "buildorder": 1,
                "name": "seabios",
                "ref": "94f4f45b8837c5e834b0ae11d368978c621c6fbc",
            },
            {
                "arches": ["aarch64", "i686", "ppc64le", "s390x", "x86_64"],
                "buildorder": 1,
                "name": "sgabios",
                "ref": "643ad1528f18937fa5fa0a021a8f25dd1e252596",
            },
            {
                "arches": ["aarch64", "i686", "ppc64le", "s390x", "x86_64"],
                "buildorder": 2,
                "name": "supermin",
                "ref": "502fabee05eb11c69d2fe29becf23e0e013a1995",
            },
            {
                "arches": ["aarch64", "i686", "ppc64le", "s390x", "x86_64"],
                "buildorder": 2,
                "name": "swtpm",
                "ref": "12e26459a3feb201950bf8d52a9af95afd601a5b",
            },
            {
                "arches": ["aarch64", "i686", "ppc64le", "s390x", "x86_64"],
                "buildorder": 6,
                "name": "virt-v2v",
                "ref": "22c887f059f0127d58f53e1d00b38c297e565890",
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
                    "arch": "aarch64",
                    "epoch": 0,
                    "name": "hivex",
                    "release": "23.module_el8.6.0+2880+7d9e3703",
                    "repositories": [
                        {"arch": "aarch64", "name": "almalinux-8-appstream"}
                    ],
                    "version": "1.3.18",
                },
                {
                    "arch": "aarch64",
                    "epoch": 0,
                    "name": "hivex-devel",
                    "release": "23.module_el8.6.0+2880+7d9e3703",
                    "repositories": [
                        {"arch": "aarch64", "name": "almalinux-8-appstream"}
                    ],
                    "version": "1.3.18",
                },
                {
                    "arch": "aarch64",
                    "epoch": 0,
                    "name": "perl-hivex",
                    "release": "23.module_el8.6.0+2880+7d9e3703",
                    "repositories": [
                        {"arch": "aarch64", "name": "almalinux-8-appstream"}
                    ],
                    "version": "1.3.18",
                },
                {
                    "arch": "aarch64",
                    "epoch": 0,
                    "name": "python3-hivex",
                    "release": "23.module_el8.6.0+2880+7d9e3703",
                    "repositories": [
                        {"arch": "aarch64", "name": "almalinux-8-appstream"}
                    ],
                    "version": "1.3.18",
                },
                {
                    "arch": "aarch64",
                    "epoch": 0,
                    "name": "ruby-hivex",
                    "release": "23.module_el8.6.0+2880+7d9e3703",
                    "repositories": [
                        {"arch": "aarch64", "name": "almalinux-8-appstream"}
                    ],
                    "version": "1.3.18",
                },
                {
                    "arch": "aarch64",
                    "epoch": 0,
                    "name": "hivex-debuginfo",
                    "release": "23.module_el8.6.0+2880+7d9e3703",
                    "repositories": [
                        {
                            "arch": "aarch64",
                            "name": "almalinux-8-appstream-debuginfo",
                        }
                    ],
                    "version": "1.3.18",
                },
                {
                    "arch": "aarch64",
                    "epoch": 0,
                    "name": "hivex-debugsource",
                    "release": "23.module_el8.6.0+2880+7d9e3703",
                    "repositories": [
                        {
                            "arch": "aarch64",
                            "name": "almalinux-8-appstream-debuginfo",
                        }
                    ],
                    "version": "1.3.18",
                },
                {
                    "arch": "aarch64",
                    "epoch": 0,
                    "name": "perl-hivex-debuginfo",
                    "release": "23.module_el8.6.0+2880+7d9e3703",
                    "repositories": [
                        {
                            "arch": "aarch64",
                            "name": "almalinux-8-appstream-debuginfo",
                        }
                    ],
                    "version": "1.3.18",
                },
                {
                    "arch": "aarch64",
                    "epoch": 0,
                    "name": "python3-hivex-debuginfo",
                    "release": "23.module_el8.6.0+2880+7d9e3703",
                    "repositories": [
                        {
                            "arch": "aarch64",
                            "name": "almalinux-8-appstream-debuginfo",
                        }
                    ],
                    "version": "1.3.18",
                },
                {
                    "arch": "aarch64",
                    "epoch": 0,
                    "name": "ruby-hivex-debuginfo",
                    "release": "23.module_el8.6.0+2880+7d9e3703",
                    "repositories": [
                        {
                            "arch": "aarch64",
                            "name": "almalinux-8-appstream-debuginfo",
                        }
                    ],
                    "version": "1.3.18",
                },
                {
                    "arch": "aarch64",
                    "epoch": 0,
                    "name": "ocaml-hivex",
                    "release": "23.module_el8.6.0+2880+7d9e3703",
                    "repositories": [
                        {"arch": "aarch64", "name": "almalinux-8-powertools"}
                    ],
                    "version": "1.3.18",
                },
                {
                    "arch": "aarch64",
                    "epoch": 0,
                    "name": "ocaml-hivex-devel",
                    "release": "23.module_el8.6.0+2880+7d9e3703",
                    "repositories": [
                        {"arch": "aarch64", "name": "almalinux-8-powertools"}
                    ],
                    "version": "1.3.18",
                },
                {
                    "arch": "aarch64",
                    "epoch": 0,
                    "name": "ocaml-hivex-debuginfo",
                    "release": "23.module_el8.6.0+2880+7d9e3703",
                    "repositories": [
                        {
                            "arch": "aarch64",
                            "name": "almalinux-8-powertools-debuginfo",
                        }
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
                    "name": "perl-hivex",
                    "release": "23.module_el8.6.0+2880+7d9e3703",
                    "repositories": [
                        {"arch": "x86_64", "name": "almalinux-8-appstream"}
                    ],
                    "version": "1.3.18",
                },
                {
                    "arch": "x86_64",
                    "epoch": 0,
                    "name": "python3-hivex",
                    "release": "23.module_el8.6.0+2880+7d9e3703",
                    "repositories": [
                        {"arch": "x86_64", "name": "almalinux-8-appstream"}
                    ],
                    "version": "1.3.18",
                },
                {
                    "arch": "x86_64",
                    "epoch": 0,
                    "name": "ruby-hivex",
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
                    "name": "perl-hivex-debuginfo",
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
                    "name": "python3-hivex-debuginfo",
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
                    "name": "ruby-hivex-debuginfo",
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
                    "name": "perl-hivex",
                    "release": "23.module_el8.6.0+2880+7d9e3703",
                    "repositories": [
                        {"arch": "x86_64", "name": "almalinux-8-powertools"}
                    ],
                    "version": "1.3.18",
                },
                {
                    "arch": "i686",
                    "epoch": 0,
                    "name": "python3-hivex",
                    "release": "23.module_el8.6.0+2880+7d9e3703",
                    "repositories": [
                        {"arch": "x86_64", "name": "almalinux-8-powertools"}
                    ],
                    "version": "1.3.18",
                },
                {
                    "arch": "i686",
                    "epoch": 0,
                    "name": "ruby-hivex",
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
                    "arch": "i686",
                    "epoch": 0,
                    "name": "perl-hivex-debuginfo",
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
                    "name": "python3-hivex-debuginfo",
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
                    "name": "ruby-hivex-debuginfo",
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
                    "name": "perl-hivex",
                    "release": "23.module_el8.6.0+2880+7d9e3703",
                    "repositories": [
                        {"arch": "ppc64le", "name": "almalinux-8-appstream"}
                    ],
                    "version": "1.3.18",
                },
                {
                    "arch": "ppc64le",
                    "epoch": 0,
                    "name": "python3-hivex",
                    "release": "23.module_el8.6.0+2880+7d9e3703",
                    "repositories": [
                        {"arch": "ppc64le", "name": "almalinux-8-appstream"}
                    ],
                    "version": "1.3.18",
                },
                {
                    "arch": "ppc64le",
                    "epoch": 0,
                    "name": "ruby-hivex",
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
                    "name": "perl-hivex-debuginfo",
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
                    "name": "python3-hivex-debuginfo",
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
                    "name": "ruby-hivex-debuginfo",
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
@pytest.mark.anyio
def mock_beholder_call(
    monkeypatch,
    beholder_virt_response: dict,
    beholder_virt_devel_response: dict,
    beholder_slof_response: dict,
    beholder_hivex_response: dict,
):
    async def func(*args, **kwargs):
        *_, endpoint = args
        if 'SLOF-20210217-1.module_el8.6.0+2880+7d9e3703.src.rpm' in endpoint:
            return beholder_slof_response
        if 'hivex-1.3.18-23.module_el8.6.0+2880+7d9e3703.src.rpm' in endpoint:
            return beholder_hivex_response
        if '/module/virt/rhel/x86_64' in endpoint:
            return beholder_virt_response
        if '/module/virt-devel/rhel/x86_64/' in endpoint:
            return beholder_virt_devel_response

    monkeypatch.setattr(MultilibProcessor, 'call_beholder', func)


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

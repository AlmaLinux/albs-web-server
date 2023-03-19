import asyncio
import hashlib
import uuid

import pytest

from alws.config import settings
from alws.schemas.build_node_schema import BuildDoneArtifact
from alws.utils.parsing import parse_rpm_nevra
from alws.utils.beholder_client import BeholderClient

modules_endpoint_response = {
    "/api/v1/distros/AlmaLinux/8/module/virt/rhel/x86_64/": {
      "arch": "x86_64",
      "artifacts": [
        {
          "packages": [
            {
              "arch": "src",
              "epoch": 0,
              "name": "hivex",
              "release": "20.module+el8.3.0+6423+e4cb6418",
              "repositories": [
                {
                  "arch": "src",
                  "name": "almalinux-8-appstream"
                }
              ],
              "version": "1.3.18"
            },
            {
              "arch": "x86_64",
              "epoch": 0,
              "name": "hivex",
              "release": "20.module+el8.3.0+6423+e4cb6418",
              "repositories": [
                {
                  "arch": "x86_64",
                  "name": "almalinux-8-appstream"
                }
              ],
              "version": "1.3.18"
            },
            {
              "arch": "x86_64",
              "epoch": 0,
              "name": "hivex-debuginfo",
              "release": "20.module+el8.3.0+6423+e4cb6418",
              "repositories": [
                {
                  "arch": "x86_64",
                  "name": "almalinux-8-appstream-debuginfo"
                }
              ],
              "version": "1.3.18"
            },
            {
              "arch": "x86_64",
              "epoch": 0,
              "name": "hivex-debugsource",
              "release": "20.module+el8.3.0+6423+e4cb6418",
              "repositories": [
                {
                  "arch": "x86_64",
                  "name": "almalinux-8-appstream-debuginfo"
                }
              ],
              "version": "1.3.18"
            },
            {
              "arch": "x86_64",
              "epoch": 0,
              "name": "hivex-devel",
              "release": "20.module+el8.3.0+6423+e4cb6418",
              "repositories": [
                {
                  "arch": "x86_64",
                  "name": "almalinux-8-appstream"
                }
              ],
              "version": "1.3.18"
            },
            {
              "arch": "x86_64",
              "epoch": 0,
              "name": "perl-hivex",
              "release": "20.module+el8.3.0+6423+e4cb6418",
              "repositories": [
                {
                  "arch": "x86_64",
                  "name": "almalinux-8-appstream"
                }
              ],
              "version": "1.3.18"
            },
            {
              "arch": "x86_64",
              "epoch": 0,
              "name": "perl-hivex-debuginfo",
              "release": "20.module+el8.3.0+6423+e4cb6418",
              "repositories": [
                {
                  "arch": "x86_64",
                  "name": "almalinux-8-appstream-debuginfo"
                }
              ],
              "version": "1.3.18"
            },
            {
              "arch": "x86_64",
              "epoch": 0,
              "name": "python3-hivex",
              "release": "20.module+el8.3.0+6423+e4cb6418",
              "repositories": [
                {
                  "arch": "x86_64",
                  "name": "almalinux-8-appstream"
                }
              ],
              "version": "1.3.18"
            },
            {
              "arch": "x86_64",
              "epoch": 0,
              "name": "python3-hivex-debuginfo",
              "release": "20.module+el8.3.0+6423+e4cb6418",
              "repositories": [
                {
                  "arch": "x86_64",
                  "name": "almalinux-8-appstream-debuginfo"
                }
              ],
              "version": "1.3.18"
            },
            {
              "arch": "x86_64",
              "epoch": 0,
              "name": "ruby-hivex",
              "release": "20.module+el8.3.0+6423+e4cb6418",
              "repositories": [
                {
                  "arch": "x86_64",
                  "name": "almalinux-8-appstream"
                }
              ],
              "version": "1.3.18"
            },
            {
              "arch": "x86_64",
              "epoch": 0,
              "name": "ruby-hivex-debuginfo",
              "release": "20.module+el8.3.0+6423+e4cb6418",
              "repositories": [
                {
                  "arch": "x86_64",
                  "name": "almalinux-8-appstream-debuginfo"
                }
              ],
              "version": "1.3.18"
            }
          ],
          "sourcerpm": {
            "epoch": 0,
            "name": "hivex",
            "release": "20.module+el8.3.0+6423+e4cb6418",
            "version": "1.3.18"
          }
        },
        {
          "packages": [
            {
              "arch": "src",
              "epoch": 1,
              "name": "libguestfs",
              "release": "25.module+el8.3.0+7421+642fe24f",
              "repositories": [
                {
                  "arch": "src",
                  "name": "almalinux-8-appstream"
                }
              ],
              "version": "1.40.2"
            },
            {
              "arch": "x86_64",
              "epoch": 1,
              "name": "libguestfs",
              "release": "25.module+el8.3.0+7421+642fe24f",
              "repositories": [
                {
                  "arch": "x86_64",
                  "name": "almalinux-8-appstream"
                }
              ],
              "version": "1.40.2"
            },
            {
              "arch": "x86_64",
              "epoch": 1,
              "name": "libguestfs-appliance",
              "release": "25.module+el8.3.0+7421+642fe24f",
              "repositories": [
                {
                  "arch": "x86_64",
                  "name": "almalinux-8-appstream"
                }
              ],
              "version": "1.40.2"
            },
            {
              "arch": "noarch",
              "epoch": 1,
              "name": "libguestfs-bash-completion",
              "release": "25.module+el8.3.0+7421+642fe24f",
              "repositories": [
                {
                  "arch": "x86_64",
                  "name": "almalinux-8-appstream"
                }
              ],
              "version": "1.40.2"
            },
            {
              "arch": "x86_64",
              "epoch": 1,
              "name": "libguestfs-debuginfo",
              "release": "25.module+el8.3.0+7421+642fe24f",
              "repositories": [
                {
                  "arch": "x86_64",
                  "name": "almalinux-8-appstream-debuginfo"
                }
              ],
              "version": "1.40.2"
            },
            {
              "arch": "x86_64",
              "epoch": 1,
              "name": "libguestfs-debugsource",
              "release": "25.module+el8.3.0+7421+642fe24f",
              "repositories": [
                {
                  "arch": "x86_64",
                  "name": "almalinux-8-appstream-debuginfo"
                }
              ],
              "version": "1.40.2"
            },
            {
              "arch": "x86_64",
              "epoch": 1,
              "name": "libguestfs-devel",
              "release": "25.module+el8.3.0+7421+642fe24f",
              "repositories": [
                {
                  "arch": "x86_64",
                  "name": "almalinux-8-appstream"
                }
              ],
              "version": "1.40.2"
            },
            {
              "arch": "x86_64",
              "epoch": 1,
              "name": "libguestfs-gfs2",
              "release": "25.module+el8.3.0+7421+642fe24f",
              "repositories": [
                {
                  "arch": "x86_64",
                  "name": "almalinux-8-appstream"
                }
              ],
              "version": "1.40.2"
            },
            {
              "arch": "x86_64",
              "epoch": 1,
              "name": "libguestfs-gobject",
              "release": "25.module+el8.3.0+7421+642fe24f",
              "repositories": [
                {
                  "arch": "x86_64",
                  "name": "almalinux-8-appstream"
                }
              ],
              "version": "1.40.2"
            },
            {
              "arch": "x86_64",
              "epoch": 1,
              "name": "libguestfs-gobject-debuginfo",
              "release": "25.module+el8.3.0+7421+642fe24f",
              "repositories": [
                {
                  "arch": "x86_64",
                  "name": "almalinux-8-appstream-debuginfo"
                }
              ],
              "version": "1.40.2"
            },
            {
              "arch": "x86_64",
              "epoch": 1,
              "name": "libguestfs-gobject-devel",
              "release": "25.module+el8.3.0+7421+642fe24f",
              "repositories": [
                {
                  "arch": "x86_64",
                  "name": "almalinux-8-appstream"
                }
              ],
              "version": "1.40.2"
            },
            {
              "arch": "noarch",
              "epoch": 1,
              "name": "libguestfs-inspect-icons",
              "release": "25.module+el8.3.0+7421+642fe24f",
              "repositories": [
                {
                  "arch": "x86_64",
                  "name": "almalinux-8-appstream"
                }
              ],
              "version": "1.40.2"
            },
            {
              "arch": "x86_64",
              "epoch": 1,
              "name": "libguestfs-java",
              "release": "25.module+el8.3.0+7421+642fe24f",
              "repositories": [
                {
                  "arch": "x86_64",
                  "name": "almalinux-8-appstream"
                }
              ],
              "version": "1.40.2"
            },
            {
              "arch": "x86_64",
              "epoch": 1,
              "name": "libguestfs-java-debuginfo",
              "release": "25.module+el8.3.0+7421+642fe24f",
              "repositories": [
                {
                  "arch": "x86_64",
                  "name": "almalinux-8-appstream-debuginfo"
                }
              ],
              "version": "1.40.2"
            },
            {
              "arch": "x86_64",
              "epoch": 1,
              "name": "libguestfs-java-devel",
              "release": "25.module+el8.3.0+7421+642fe24f",
              "repositories": [
                {
                  "arch": "x86_64",
                  "name": "almalinux-8-appstream"
                }
              ],
              "version": "1.40.2"
            },
            {
              "arch": "noarch",
              "epoch": 1,
              "name": "libguestfs-javadoc",
              "release": "25.module+el8.3.0+7421+642fe24f",
              "repositories": [
                {
                  "arch": "x86_64",
                  "name": "almalinux-8-appstream"
                }
              ],
              "version": "1.40.2"
            },
            {
              "arch": "noarch",
              "epoch": 1,
              "name": "libguestfs-man-pages-ja",
              "release": "25.module+el8.3.0+7421+642fe24f",
              "repositories": [
                {
                  "arch": "x86_64",
                  "name": "almalinux-8-appstream"
                }
              ],
              "version": "1.40.2"
            },
            {
              "arch": "noarch",
              "epoch": 1,
              "name": "libguestfs-man-pages-uk",
              "release": "25.module+el8.3.0+7421+642fe24f",
              "repositories": [
                {
                  "arch": "x86_64",
                  "name": "almalinux-8-appstream"
                }
              ],
              "version": "1.40.2"
            },
            {
              "arch": "x86_64",
              "epoch": 1,
              "name": "libguestfs-rescue",
              "release": "25.module+el8.3.0+7421+642fe24f",
              "repositories": [
                {
                  "arch": "x86_64",
                  "name": "almalinux-8-appstream"
                }
              ],
              "version": "1.40.2"
            },
            {
              "arch": "x86_64",
              "epoch": 1,
              "name": "libguestfs-rsync",
              "release": "25.module+el8.3.0+7421+642fe24f",
              "repositories": [
                {
                  "arch": "x86_64",
                  "name": "almalinux-8-appstream"
                }
              ],
              "version": "1.40.2"
            },
            {
              "arch": "noarch",
              "epoch": 1,
              "name": "libguestfs-tools",
              "release": "25.module+el8.3.0+7421+642fe24f",
              "repositories": [
                {
                  "arch": "x86_64",
                  "name": "almalinux-8-appstream"
                }
              ],
              "version": "1.40.2"
            },
            {
              "arch": "x86_64",
              "epoch": 1,
              "name": "libguestfs-tools-c",
              "release": "25.module+el8.3.0+7421+642fe24f",
              "repositories": [
                {
                  "arch": "x86_64",
                  "name": "almalinux-8-appstream"
                }
              ],
              "version": "1.40.2"
            },
            {
              "arch": "x86_64",
              "epoch": 1,
              "name": "libguestfs-tools-c-debuginfo",
              "release": "25.module+el8.3.0+7421+642fe24f",
              "repositories": [
                {
                  "arch": "x86_64",
                  "name": "almalinux-8-appstream-debuginfo"
                }
              ],
              "version": "1.40.2"
            },
            {
              "arch": "x86_64",
              "epoch": 1,
              "name": "libguestfs-xfs",
              "release": "25.module+el8.3.0+7421+642fe24f",
              "repositories": [
                {
                  "arch": "x86_64",
                  "name": "almalinux-8-appstream"
                }
              ],
              "version": "1.40.2"
            },
            {
              "arch": "x86_64",
              "epoch": 1,
              "name": "lua-guestfs",
              "release": "25.module+el8.3.0+7421+642fe24f",
              "repositories": [
                {
                  "arch": "x86_64",
                  "name": "almalinux-8-appstream"
                }
              ],
              "version": "1.40.2"
            },
            {
              "arch": "x86_64",
              "epoch": 1,
              "name": "lua-guestfs-debuginfo",
              "release": "25.module+el8.3.0+7421+642fe24f",
              "repositories": [
                {
                  "arch": "x86_64",
                  "name": "almalinux-8-appstream-debuginfo"
                }
              ],
              "version": "1.40.2"
            },
            {
              "arch": "x86_64",
              "epoch": 1,
              "name": "perl-Sys-Guestfs",
              "release": "25.module+el8.3.0+7421+642fe24f",
              "repositories": [
                {
                  "arch": "x86_64",
                  "name": "almalinux-8-appstream"
                }
              ],
              "version": "1.40.2"
            },
            {
              "arch": "x86_64",
              "epoch": 1,
              "name": "perl-Sys-Guestfs-debuginfo",
              "release": "25.module+el8.3.0+7421+642fe24f",
              "repositories": [
                {
                  "arch": "x86_64",
                  "name": "almalinux-8-appstream-debuginfo"
                }
              ],
              "version": "1.40.2"
            },
            {
              "arch": "x86_64",
              "epoch": 1,
              "name": "python3-libguestfs",
              "release": "25.module+el8.3.0+7421+642fe24f",
              "repositories": [
                {
                  "arch": "x86_64",
                  "name": "almalinux-8-appstream"
                }
              ],
              "version": "1.40.2"
            },
            {
              "arch": "x86_64",
              "epoch": 1,
              "name": "python3-libguestfs-debuginfo",
              "release": "25.module+el8.3.0+7421+642fe24f",
              "repositories": [
                {
                  "arch": "x86_64",
                  "name": "almalinux-8-appstream-debuginfo"
                }
              ],
              "version": "1.40.2"
            },
            {
              "arch": "x86_64",
              "epoch": 1,
              "name": "ruby-libguestfs",
              "release": "25.module+el8.3.0+7421+642fe24f",
              "repositories": [
                {
                  "arch": "x86_64",
                  "name": "almalinux-8-appstream"
                }
              ],
              "version": "1.40.2"
            },
            {
              "arch": "x86_64",
              "epoch": 1,
              "name": "ruby-libguestfs-debuginfo",
              "release": "25.module+el8.3.0+7421+642fe24f",
              "repositories": [
                {
                  "arch": "x86_64",
                  "name": "almalinux-8-appstream-debuginfo"
                }
              ],
              "version": "1.40.2"
            },
            {
              "arch": "x86_64",
              "epoch": 1,
              "name": "virt-dib",
              "release": "25.module+el8.3.0+7421+642fe24f",
              "repositories": [
                {
                  "arch": "x86_64",
                  "name": "almalinux-8-appstream"
                }
              ],
              "version": "1.40.2"
            },
            {
              "arch": "x86_64",
              "epoch": 1,
              "name": "virt-dib-debuginfo",
              "release": "25.module+el8.3.0+7421+642fe24f",
              "repositories": [
                {
                  "arch": "x86_64",
                  "name": "almalinux-8-appstream-debuginfo"
                }
              ],
              "version": "1.40.2"
            }
          ],
          "sourcerpm": {
            "epoch": 1,
            "name": "libguestfs",
            "release": "25.module+el8.3.0+7421+642fe24f",
            "version": "1.40.2"
          }
        },
        {
          "packages": [
            {
              "arch": "src",
              "epoch": 0,
              "name": "libguestfs-winsupport",
              "release": "1.module+el8.3.0+6423+e4cb6418",
              "repositories": [
                {
                  "arch": "src",
                  "name": "almalinux-8-appstream"
                }
              ],
              "version": "8.2"
            },
            {
              "arch": "x86_64",
              "epoch": 0,
              "name": "libguestfs-winsupport",
              "release": "1.module+el8.3.0+6423+e4cb6418",
              "repositories": [
                {
                  "arch": "x86_64",
                  "name": "almalinux-8-appstream"
                }
              ],
              "version": "8.2"
            }
          ],
          "sourcerpm": {
            "epoch": 0,
            "name": "libguestfs-winsupport",
            "release": "1.module+el8.3.0+6423+e4cb6418",
            "version": "8.2"
          }
        },
        {
          "packages": [
            {
              "arch": "src",
              "epoch": 0,
              "name": "libiscsi",
              "release": "8.module+el8.1.0+4066+0f1aadab",
              "repositories": [
                {
                  "arch": "src",
                  "name": "almalinux-8-appstream"
                }
              ],
              "version": "1.18.0"
            },
            {
              "arch": "x86_64",
              "epoch": 0,
              "name": "libiscsi",
              "release": "8.module+el8.1.0+4066+0f1aadab",
              "repositories": [
                {
                  "arch": "x86_64",
                  "name": "almalinux-8-appstream"
                }
              ],
              "version": "1.18.0"
            },
            {
              "arch": "x86_64",
              "epoch": 0,
              "name": "libiscsi-debuginfo",
              "release": "8.module+el8.1.0+4066+0f1aadab",
              "repositories": [
                {
                  "arch": "x86_64",
                  "name": "almalinux-8-appstream-debuginfo"
                }
              ],
              "version": "1.18.0"
            },
            {
              "arch": "x86_64",
              "epoch": 0,
              "name": "libiscsi-debugsource",
              "release": "8.module+el8.1.0+4066+0f1aadab",
              "repositories": [
                {
                  "arch": "x86_64",
                  "name": "almalinux-8-appstream-debuginfo"
                }
              ],
              "version": "1.18.0"
            },
            {
              "arch": "x86_64",
              "epoch": 0,
              "name": "libiscsi-devel",
              "release": "8.module+el8.1.0+4066+0f1aadab",
              "repositories": [
                {
                  "arch": "x86_64",
                  "name": "almalinux-8-appstream"
                }
              ],
              "version": "1.18.0"
            },
            {
              "arch": "x86_64",
              "epoch": 0,
              "name": "libiscsi-utils",
              "release": "8.module+el8.1.0+4066+0f1aadab",
              "repositories": [
                {
                  "arch": "x86_64",
                  "name": "almalinux-8-appstream"
                }
              ],
              "version": "1.18.0"
            },
            {
              "arch": "x86_64",
              "epoch": 0,
              "name": "libiscsi-utils-debuginfo",
              "release": "8.module+el8.1.0+4066+0f1aadab",
              "repositories": [
                {
                  "arch": "x86_64",
                  "name": "almalinux-8-appstream-debuginfo"
                }
              ],
              "version": "1.18.0"
            }
          ],
          "sourcerpm": {
            "epoch": 0,
            "name": "libiscsi",
            "release": "8.module+el8.1.0+4066+0f1aadab",
            "version": "1.18.0"
          }
        },
        {
          "packages": [
            {
              "arch": "src",
              "epoch": 0,
              "name": "libnbd",
              "release": "1.module+el8.3.0+7353+9de0a3cc",
              "repositories": [
                {
                  "arch": "src",
                  "name": "almalinux-8-appstream"
                }
              ],
              "version": "1.2.2"
            },
            {
              "arch": "x86_64",
              "epoch": 0,
              "name": "libnbd",
              "release": "1.module+el8.3.0+7353+9de0a3cc",
              "repositories": [
                {
                  "arch": "x86_64",
                  "name": "almalinux-8-appstream"
                }
              ],
              "version": "1.2.2"
            },
            {
              "arch": "noarch",
              "epoch": 0,
              "name": "libnbd-bash-completion",
              "release": "1.module+el8.3.0+7353+9de0a3cc",
              "repositories": [
                {
                  "arch": "x86_64",
                  "name": "almalinux-8-appstream"
                }
              ],
              "version": "1.2.2"
            },
            {
              "arch": "x86_64",
              "epoch": 0,
              "name": "libnbd-debuginfo",
              "release": "1.module+el8.3.0+7353+9de0a3cc",
              "repositories": [
                {
                  "arch": "x86_64",
                  "name": "almalinux-8-appstream-debuginfo"
                }
              ],
              "version": "1.2.2"
            },
            {
              "arch": "x86_64",
              "epoch": 0,
              "name": "libnbd-debugsource",
              "release": "1.module+el8.3.0+7353+9de0a3cc",
              "repositories": [
                {
                  "arch": "x86_64",
                  "name": "almalinux-8-appstream-debuginfo"
                }
              ],
              "version": "1.2.2"
            },
            {
              "arch": "x86_64",
              "epoch": 0,
              "name": "libnbd-devel",
              "release": "1.module+el8.3.0+7353+9de0a3cc",
              "repositories": [
                {
                  "arch": "x86_64",
                  "name": "almalinux-8-appstream"
                }
              ],
              "version": "1.2.2"
            },
            {
              "arch": "x86_64",
              "epoch": 0,
              "name": "nbdfuse",
              "release": "1.module+el8.3.0+7353+9de0a3cc",
              "repositories": [
                {
                  "arch": "x86_64",
                  "name": "almalinux-8-appstream"
                }
              ],
              "version": "1.2.2"
            },
            {
              "arch": "x86_64",
              "epoch": 0,
              "name": "nbdfuse-debuginfo",
              "release": "1.module+el8.3.0+7353+9de0a3cc",
              "repositories": [
                {
                  "arch": "x86_64",
                  "name": "almalinux-8-appstream-debuginfo"
                }
              ],
              "version": "1.2.2"
            },
            {
              "arch": "x86_64",
              "epoch": 0,
              "name": "python3-libnbd",
              "release": "1.module+el8.3.0+7353+9de0a3cc",
              "repositories": [
                {
                  "arch": "x86_64",
                  "name": "almalinux-8-appstream"
                }
              ],
              "version": "1.2.2"
            },
            {
              "arch": "x86_64",
              "epoch": 0,
              "name": "python3-libnbd-debuginfo",
              "release": "1.module+el8.3.0+7353+9de0a3cc",
              "repositories": [
                {
                  "arch": "x86_64",
                  "name": "almalinux-8-appstream-debuginfo"
                }
              ],
              "version": "1.2.2"
            }
          ],
          "sourcerpm": {
            "epoch": 0,
            "name": "libnbd",
            "release": "1.module+el8.3.0+7353+9de0a3cc",
            "version": "1.2.2"
          }
        },
        {
          "packages": [
            {
              "arch": "src",
              "epoch": 0,
              "name": "libvirt",
              "release": "28.module+el8.3.0+7827+5e65edd7",
              "repositories": [
                {
                  "arch": "src",
                  "name": "almalinux-8-appstream"
                }
              ],
              "version": "6.0.0"
            },
            {
              "arch": "x86_64",
              "epoch": 0,
              "name": "libvirt",
              "release": "28.module+el8.3.0+7827+5e65edd7",
              "repositories": [
                {
                  "arch": "x86_64",
                  "name": "almalinux-8-appstream"
                }
              ],
              "version": "6.0.0"
            },
            {
              "arch": "x86_64",
              "epoch": 0,
              "name": "libvirt-client",
              "release": "28.module+el8.3.0+7827+5e65edd7",
              "repositories": [
                {
                  "arch": "x86_64",
                  "name": "almalinux-8-appstream"
                }
              ],
              "version": "6.0.0"
            },
            {
              "arch": "x86_64",
              "epoch": 0,
              "name": "libvirt-client-debuginfo",
              "release": "28.module+el8.3.0+7827+5e65edd7",
              "repositories": [
                {
                  "arch": "x86_64",
                  "name": "almalinux-8-appstream-debuginfo"
                }
              ],
              "version": "6.0.0"
            },
            {
              "arch": "x86_64",
              "epoch": 0,
              "name": "libvirt-daemon",
              "release": "28.module+el8.3.0+7827+5e65edd7",
              "repositories": [
                {
                  "arch": "x86_64",
                  "name": "almalinux-8-appstream"
                }
              ],
              "version": "6.0.0"
            },
            {
              "arch": "x86_64",
              "epoch": 0,
              "name": "libvirt-daemon-config-network",
              "release": "28.module+el8.3.0+7827+5e65edd7",
              "repositories": [
                {
                  "arch": "x86_64",
                  "name": "almalinux-8-appstream"
                }
              ],
              "version": "6.0.0"
            },
            {
              "arch": "x86_64",
              "epoch": 0,
              "name": "libvirt-daemon-config-nwfilter",
              "release": "28.module+el8.3.0+7827+5e65edd7",
              "repositories": [
                {
                  "arch": "x86_64",
                  "name": "almalinux-8-appstream"
                }
              ],
              "version": "6.0.0"
            },
            {
              "arch": "x86_64",
              "epoch": 0,
              "name": "libvirt-daemon-debuginfo",
              "release": "28.module+el8.3.0+7827+5e65edd7",
              "repositories": [
                {
                  "arch": "x86_64",
                  "name": "almalinux-8-appstream-debuginfo"
                }
              ],
              "version": "6.0.0"
            },
            {
              "arch": "x86_64",
              "epoch": 0,
              "name": "libvirt-daemon-driver-interface",
              "release": "28.module+el8.3.0+7827+5e65edd7",
              "repositories": [
                {
                  "arch": "x86_64",
                  "name": "almalinux-8-appstream"
                }
              ],
              "version": "6.0.0"
            },
            {
              "arch": "x86_64",
              "epoch": 0,
              "name": "libvirt-daemon-driver-interface-debuginfo",
              "release": "28.module+el8.3.0+7827+5e65edd7",
              "repositories": [
                {
                  "arch": "x86_64",
                  "name": "almalinux-8-appstream-debuginfo"
                }
              ],
              "version": "6.0.0"
            },
            {
              "arch": "x86_64",
              "epoch": 0,
              "name": "libvirt-daemon-driver-network",
              "release": "28.module+el8.3.0+7827+5e65edd7",
              "repositories": [
                {
                  "arch": "x86_64",
                  "name": "almalinux-8-appstream"
                }
              ],
              "version": "6.0.0"
            },
            {
              "arch": "x86_64",
              "epoch": 0,
              "name": "libvirt-daemon-driver-network-debuginfo",
              "release": "28.module+el8.3.0+7827+5e65edd7",
              "repositories": [
                {
                  "arch": "x86_64",
                  "name": "almalinux-8-appstream-debuginfo"
                }
              ],
              "version": "6.0.0"
            },
            {
              "arch": "x86_64",
              "epoch": 0,
              "name": "libvirt-daemon-driver-nodedev",
              "release": "28.module+el8.3.0+7827+5e65edd7",
              "repositories": [
                {
                  "arch": "x86_64",
                  "name": "almalinux-8-appstream"
                }
              ],
              "version": "6.0.0"
            },
            {
              "arch": "x86_64",
              "epoch": 0,
              "name": "libvirt-daemon-driver-nodedev-debuginfo",
              "release": "28.module+el8.3.0+7827+5e65edd7",
              "repositories": [
                {
                  "arch": "x86_64",
                  "name": "almalinux-8-appstream-debuginfo"
                }
              ],
              "version": "6.0.0"
            },
            {
              "arch": "x86_64",
              "epoch": 0,
              "name": "libvirt-daemon-driver-nwfilter",
              "release": "28.module+el8.3.0+7827+5e65edd7",
              "repositories": [
                {
                  "arch": "x86_64",
                  "name": "almalinux-8-appstream"
                }
              ],
              "version": "6.0.0"
            },
            {
              "arch": "x86_64",
              "epoch": 0,
              "name": "libvirt-daemon-driver-nwfilter-debuginfo",
              "release": "28.module+el8.3.0+7827+5e65edd7",
              "repositories": [
                {
                  "arch": "x86_64",
                  "name": "almalinux-8-appstream-debuginfo"
                }
              ],
              "version": "6.0.0"
            },
            {
              "arch": "x86_64",
              "epoch": 0,
              "name": "libvirt-daemon-driver-qemu",
              "release": "28.module+el8.3.0+7827+5e65edd7",
              "repositories": [
                {
                  "arch": "x86_64",
                  "name": "almalinux-8-appstream"
                }
              ],
              "version": "6.0.0"
            },
            {
              "arch": "x86_64",
              "epoch": 0,
              "name": "libvirt-daemon-driver-qemu-debuginfo",
              "release": "28.module+el8.3.0+7827+5e65edd7",
              "repositories": [
                {
                  "arch": "x86_64",
                  "name": "almalinux-8-appstream-debuginfo"
                }
              ],
              "version": "6.0.0"
            },
            {
              "arch": "x86_64",
              "epoch": 0,
              "name": "libvirt-daemon-driver-secret",
              "release": "28.module+el8.3.0+7827+5e65edd7",
              "repositories": [
                {
                  "arch": "x86_64",
                  "name": "almalinux-8-appstream"
                }
              ],
              "version": "6.0.0"
            },
            {
              "arch": "x86_64",
              "epoch": 0,
              "name": "libvirt-daemon-driver-secret-debuginfo",
              "release": "28.module+el8.3.0+7827+5e65edd7",
              "repositories": [
                {
                  "arch": "x86_64",
                  "name": "almalinux-8-appstream-debuginfo"
                }
              ],
              "version": "6.0.0"
            },
            {
              "arch": "x86_64",
              "epoch": 0,
              "name": "libvirt-daemon-driver-storage",
              "release": "28.module+el8.3.0+7827+5e65edd7",
              "repositories": [
                {
                  "arch": "x86_64",
                  "name": "almalinux-8-appstream"
                }
              ],
              "version": "6.0.0"
            },
            {
              "arch": "x86_64",
              "epoch": 0,
              "name": "libvirt-daemon-driver-storage-core",
              "release": "28.module+el8.3.0+7827+5e65edd7",
              "repositories": [
                {
                  "arch": "x86_64",
                  "name": "almalinux-8-appstream"
                }
              ],
              "version": "6.0.0"
            },
            {
              "arch": "x86_64",
              "epoch": 0,
              "name": "libvirt-daemon-driver-storage-core-debuginfo",
              "release": "28.module+el8.3.0+7827+5e65edd7",
              "repositories": [
                {
                  "arch": "x86_64",
                  "name": "almalinux-8-appstream-debuginfo"
                }
              ],
              "version": "6.0.0"
            },
            {
              "arch": "x86_64",
              "epoch": 0,
              "name": "libvirt-daemon-driver-storage-disk",
              "release": "28.module+el8.3.0+7827+5e65edd7",
              "repositories": [
                {
                  "arch": "x86_64",
                  "name": "almalinux-8-appstream"
                }
              ],
              "version": "6.0.0"
            },
            {
              "arch": "x86_64",
              "epoch": 0,
              "name": "libvirt-daemon-driver-storage-disk-debuginfo",
              "release": "28.module+el8.3.0+7827+5e65edd7",
              "repositories": [
                {
                  "arch": "x86_64",
                  "name": "almalinux-8-appstream-debuginfo"
                }
              ],
              "version": "6.0.0"
            },
            {
              "arch": "x86_64",
              "epoch": 0,
              "name": "libvirt-daemon-driver-storage-gluster",
              "release": "28.module+el8.3.0+7827+5e65edd7",
              "repositories": [
                {
                  "arch": "x86_64",
                  "name": "almalinux-8-appstream"
                }
              ],
              "version": "6.0.0"
            },
            {
              "arch": "x86_64",
              "epoch": 0,
              "name": "libvirt-daemon-driver-storage-gluster-debuginfo",
              "release": "28.module+el8.3.0+7827+5e65edd7",
              "repositories": [
                {
                  "arch": "x86_64",
                  "name": "almalinux-8-appstream-debuginfo"
                }
              ],
              "version": "6.0.0"
            },
            {
              "arch": "x86_64",
              "epoch": 0,
              "name": "libvirt-daemon-driver-storage-iscsi",
              "release": "28.module+el8.3.0+7827+5e65edd7",
              "repositories": [
                {
                  "arch": "x86_64",
                  "name": "almalinux-8-appstream"
                }
              ],
              "version": "6.0.0"
            },
            {
              "arch": "x86_64",
              "epoch": 0,
              "name": "libvirt-daemon-driver-storage-iscsi-debuginfo",
              "release": "28.module+el8.3.0+7827+5e65edd7",
              "repositories": [
                {
                  "arch": "x86_64",
                  "name": "almalinux-8-appstream-debuginfo"
                }
              ],
              "version": "6.0.0"
            },
            {
              "arch": "x86_64",
              "epoch": 0,
              "name": "libvirt-daemon-driver-storage-iscsi-direct",
              "release": "28.module+el8.3.0+7827+5e65edd7",
              "repositories": [
                {
                  "arch": "x86_64",
                  "name": "almalinux-8-appstream"
                }
              ],
              "version": "6.0.0"
            },
            {
              "arch": "x86_64",
              "epoch": 0,
              "name": "libvirt-daemon-driver-storage-iscsi-direct-debuginfo",
              "release": "28.module+el8.3.0+7827+5e65edd7",
              "repositories": [
                {
                  "arch": "x86_64",
                  "name": "almalinux-8-appstream-debuginfo"
                }
              ],
              "version": "6.0.0"
            },
            {
              "arch": "x86_64",
              "epoch": 0,
              "name": "libvirt-daemon-driver-storage-logical",
              "release": "28.module+el8.3.0+7827+5e65edd7",
              "repositories": [
                {
                  "arch": "x86_64",
                  "name": "almalinux-8-appstream"
                }
              ],
              "version": "6.0.0"
            },
            {
              "arch": "x86_64",
              "epoch": 0,
              "name": "libvirt-daemon-driver-storage-logical-debuginfo",
              "release": "28.module+el8.3.0+7827+5e65edd7",
              "repositories": [
                {
                  "arch": "x86_64",
                  "name": "almalinux-8-appstream-debuginfo"
                }
              ],
              "version": "6.0.0"
            },
            {
              "arch": "x86_64",
              "epoch": 0,
              "name": "libvirt-daemon-driver-storage-mpath",
              "release": "28.module+el8.3.0+7827+5e65edd7",
              "repositories": [
                {
                  "arch": "x86_64",
                  "name": "almalinux-8-appstream"
                }
              ],
              "version": "6.0.0"
            },
            {
              "arch": "x86_64",
              "epoch": 0,
              "name": "libvirt-daemon-driver-storage-mpath-debuginfo",
              "release": "28.module+el8.3.0+7827+5e65edd7",
              "repositories": [
                {
                  "arch": "x86_64",
                  "name": "almalinux-8-appstream-debuginfo"
                }
              ],
              "version": "6.0.0"
            },
            {
              "arch": "x86_64",
              "epoch": 0,
              "name": "libvirt-daemon-driver-storage-rbd",
              "release": "28.module+el8.3.0+7827+5e65edd7",
              "repositories": [
                {
                  "arch": "x86_64",
                  "name": "almalinux-8-appstream"
                }
              ],
              "version": "6.0.0"
            },
            {
              "arch": "x86_64",
              "epoch": 0,
              "name": "libvirt-daemon-driver-storage-rbd-debuginfo",
              "release": "28.module+el8.3.0+7827+5e65edd7",
              "repositories": [
                {
                  "arch": "x86_64",
                  "name": "almalinux-8-appstream-debuginfo"
                }
              ],
              "version": "6.0.0"
            },
            {
              "arch": "x86_64",
              "epoch": 0,
              "name": "libvirt-daemon-driver-storage-scsi",
              "release": "28.module+el8.3.0+7827+5e65edd7",
              "repositories": [
                {
                  "arch": "x86_64",
                  "name": "almalinux-8-appstream"
                }
              ],
              "version": "6.0.0"
            },
            {
              "arch": "x86_64",
              "epoch": 0,
              "name": "libvirt-daemon-driver-storage-scsi-debuginfo",
              "release": "28.module+el8.3.0+7827+5e65edd7",
              "repositories": [
                {
                  "arch": "x86_64",
                  "name": "almalinux-8-appstream-debuginfo"
                }
              ],
              "version": "6.0.0"
            },
            {
              "arch": "x86_64",
              "epoch": 0,
              "name": "libvirt-daemon-kvm",
              "release": "28.module+el8.3.0+7827+5e65edd7",
              "repositories": [
                {
                  "arch": "x86_64",
                  "name": "almalinux-8-appstream"
                }
              ],
              "version": "6.0.0"
            },
            {
              "arch": "x86_64",
              "epoch": 0,
              "name": "libvirt-debuginfo",
              "release": "28.module+el8.3.0+7827+5e65edd7",
              "repositories": [
                {
                  "arch": "x86_64",
                  "name": "almalinux-8-appstream-debuginfo"
                }
              ],
              "version": "6.0.0"
            },
            {
              "arch": "x86_64",
              "epoch": 0,
              "name": "libvirt-debugsource",
              "release": "28.module+el8.3.0+7827+5e65edd7",
              "repositories": [
                {
                  "arch": "x86_64",
                  "name": "almalinux-8-appstream-debuginfo"
                }
              ],
              "version": "6.0.0"
            },
            {
              "arch": "x86_64",
              "epoch": 0,
              "name": "libvirt-devel",
              "release": "28.module+el8.3.0+7827+5e65edd7",
              "repositories": [
                {
                  "arch": "x86_64",
                  "name": "almalinux-8-appstream"
                }
              ],
              "version": "6.0.0"
            },
            {
              "arch": "x86_64",
              "epoch": 0,
              "name": "libvirt-docs",
              "release": "28.module+el8.3.0+7827+5e65edd7",
              "repositories": [
                {
                  "arch": "x86_64",
                  "name": "almalinux-8-appstream"
                }
              ],
              "version": "6.0.0"
            },
            {
              "arch": "x86_64",
              "epoch": 0,
              "name": "libvirt-libs",
              "release": "28.module+el8.3.0+7827+5e65edd7",
              "repositories": [
                {
                  "arch": "x86_64",
                  "name": "almalinux-8-appstream"
                }
              ],
              "version": "6.0.0"
            },
            {
              "arch": "x86_64",
              "epoch": 0,
              "name": "libvirt-libs-debuginfo",
              "release": "28.module+el8.3.0+7827+5e65edd7",
              "repositories": [
                {
                  "arch": "x86_64",
                  "name": "almalinux-8-appstream-debuginfo"
                }
              ],
              "version": "6.0.0"
            },
            {
              "arch": "x86_64",
              "epoch": 0,
              "name": "libvirt-lock-sanlock",
              "release": "28.module+el8.3.0+7827+5e65edd7",
              "repositories": [
                {
                  "arch": "x86_64",
                  "name": "almalinux-8-appstream"
                }
              ],
              "version": "6.0.0"
            },
            {
              "arch": "x86_64",
              "epoch": 0,
              "name": "libvirt-lock-sanlock-debuginfo",
              "release": "28.module+el8.3.0+7827+5e65edd7",
              "repositories": [
                {
                  "arch": "x86_64",
                  "name": "almalinux-8-appstream-debuginfo"
                }
              ],
              "version": "6.0.0"
            },
            {
              "arch": "x86_64",
              "epoch": 0,
              "name": "libvirt-nss",
              "release": "28.module+el8.3.0+7827+5e65edd7",
              "repositories": [
                {
                  "arch": "x86_64",
                  "name": "almalinux-8-appstream"
                }
              ],
              "version": "6.0.0"
            },
            {
              "arch": "x86_64",
              "epoch": 0,
              "name": "libvirt-nss-debuginfo",
              "release": "28.module+el8.3.0+7827+5e65edd7",
              "repositories": [
                {
                  "arch": "x86_64",
                  "name": "almalinux-8-appstream-debuginfo"
                }
              ],
              "version": "6.0.0"
            },
            {
              "arch": "x86_64",
              "epoch": 0,
              "name": "libvirt-wireshark",
              "release": "28.module+el8.3.0+7827+5e65edd7",
              "repositories": [
                {
                  "arch": "x86_64",
                  "name": "almalinux-8-appstream"
                }
              ],
              "version": "6.0.0"
            },
            {
              "arch": "x86_64",
              "epoch": 0,
              "name": "libvirt-wireshark-debuginfo",
              "release": "28.module+el8.3.0+7827+5e65edd7",
              "repositories": [
                {
                  "arch": "x86_64",
                  "name": "almalinux-8-appstream-debuginfo"
                }
              ],
              "version": "6.0.0"
            }
          ],
          "sourcerpm": {
            "epoch": 0,
            "name": "libvirt",
            "release": "28.module+el8.3.0+7827+5e65edd7",
            "version": "6.0.0"
          }
        },
        {
          "packages": [
            {
              "arch": "src",
              "epoch": 0,
              "name": "libvirt-dbus",
              "release": "2.module+el8.3.0+6423+e4cb6418",
              "repositories": [
                {
                  "arch": "src",
                  "name": "almalinux-8-appstream"
                }
              ],
              "version": "1.3.0"
            },
            {
              "arch": "x86_64",
              "epoch": 0,
              "name": "libvirt-dbus",
              "release": "2.module+el8.3.0+6423+e4cb6418",
              "repositories": [
                {
                  "arch": "x86_64",
                  "name": "almalinux-8-appstream"
                }
              ],
              "version": "1.3.0"
            },
            {
              "arch": "x86_64",
              "epoch": 0,
              "name": "libvirt-dbus-debuginfo",
              "release": "2.module+el8.3.0+6423+e4cb6418",
              "repositories": [
                {
                  "arch": "x86_64",
                  "name": "almalinux-8-appstream-debuginfo"
                }
              ],
              "version": "1.3.0"
            },
            {
              "arch": "x86_64",
              "epoch": 0,
              "name": "libvirt-dbus-debugsource",
              "release": "2.module+el8.3.0+6423+e4cb6418",
              "repositories": [
                {
                  "arch": "x86_64",
                  "name": "almalinux-8-appstream-debuginfo"
                }
              ],
              "version": "1.3.0"
            }
          ],
          "sourcerpm": {
            "epoch": 0,
            "name": "libvirt-dbus",
            "release": "2.module+el8.3.0+6423+e4cb6418",
            "version": "1.3.0"
          }
        },
        {
          "packages": [
            {
              "arch": "src",
              "epoch": 0,
              "name": "libvirt-python",
              "release": "1.module+el8.3.0+6423+e4cb6418",
              "repositories": [
                {
                  "arch": "src",
                  "name": "almalinux-8-appstream"
                }
              ],
              "version": "6.0.0"
            },
            {
              "arch": "x86_64",
              "epoch": 0,
              "name": "libvirt-python-debugsource",
              "release": "1.module+el8.3.0+6423+e4cb6418",
              "repositories": [
                {
                  "arch": "x86_64",
                  "name": "almalinux-8-appstream-debuginfo"
                }
              ],
              "version": "6.0.0"
            },
            {
              "arch": "x86_64",
              "epoch": 0,
              "name": "python3-libvirt",
              "release": "1.module+el8.3.0+6423+e4cb6418",
              "repositories": [
                {
                  "arch": "x86_64",
                  "name": "almalinux-8-appstream"
                }
              ],
              "version": "6.0.0"
            },
            {
              "arch": "x86_64",
              "epoch": 0,
              "name": "python3-libvirt-debuginfo",
              "release": "1.module+el8.3.0+6423+e4cb6418",
              "repositories": [
                {
                  "arch": "x86_64",
                  "name": "almalinux-8-appstream-debuginfo"
                }
              ],
              "version": "6.0.0"
            }
          ],
          "sourcerpm": {
            "epoch": 0,
            "name": "libvirt-python",
            "release": "1.module+el8.3.0+6423+e4cb6418",
            "version": "6.0.0"
          }
        },
        {
          "packages": [
            {
              "arch": "src",
              "epoch": 0,
              "name": "nbdkit",
              "release": "4.module+el8.3.0+6922+fd575af8",
              "repositories": [
                {
                  "arch": "src",
                  "name": "almalinux-8-appstream"
                }
              ],
              "version": "1.16.2"
            },
            {
              "arch": "x86_64",
              "epoch": 0,
              "name": "nbdkit",
              "release": "4.module+el8.3.0+6922+fd575af8",
              "repositories": [
                {
                  "arch": "x86_64",
                  "name": "almalinux-8-appstream"
                }
              ],
              "version": "1.16.2"
            },
            {
              "arch": "noarch",
              "epoch": 0,
              "name": "nbdkit-bash-completion",
              "release": "4.module+el8.3.0+6922+fd575af8",
              "repositories": [
                {
                  "arch": "x86_64",
                  "name": "almalinux-8-appstream"
                }
              ],
              "version": "1.16.2"
            },
            {
              "arch": "x86_64",
              "epoch": 0,
              "name": "nbdkit-basic-filters",
              "release": "4.module+el8.3.0+6922+fd575af8",
              "repositories": [
                {
                  "arch": "x86_64",
                  "name": "almalinux-8-appstream"
                }
              ],
              "version": "1.16.2"
            },
            {
              "arch": "x86_64",
              "epoch": 0,
              "name": "nbdkit-basic-filters-debuginfo",
              "release": "4.module+el8.3.0+6922+fd575af8",
              "repositories": [
                {
                  "arch": "x86_64",
                  "name": "almalinux-8-appstream-debuginfo"
                }
              ],
              "version": "1.16.2"
            },
            {
              "arch": "x86_64",
              "epoch": 0,
              "name": "nbdkit-basic-plugins",
              "release": "4.module+el8.3.0+6922+fd575af8",
              "repositories": [
                {
                  "arch": "x86_64",
                  "name": "almalinux-8-appstream"
                }
              ],
              "version": "1.16.2"
            },
            {
              "arch": "x86_64",
              "epoch": 0,
              "name": "nbdkit-basic-plugins-debuginfo",
              "release": "4.module+el8.3.0+6922+fd575af8",
              "repositories": [
                {
                  "arch": "x86_64",
                  "name": "almalinux-8-appstream-debuginfo"
                }
              ],
              "version": "1.16.2"
            },
            {
              "arch": "x86_64",
              "epoch": 0,
              "name": "nbdkit-curl-plugin",
              "release": "4.module+el8.3.0+6922+fd575af8",
              "repositories": [
                {
                  "arch": "x86_64",
                  "name": "almalinux-8-appstream"
                }
              ],
              "version": "1.16.2"
            },
            {
              "arch": "x86_64",
              "epoch": 0,
              "name": "nbdkit-curl-plugin-debuginfo",
              "release": "4.module+el8.3.0+6922+fd575af8",
              "repositories": [
                {
                  "arch": "x86_64",
                  "name": "almalinux-8-appstream-debuginfo"
                }
              ],
              "version": "1.16.2"
            },
            {
              "arch": "x86_64",
              "epoch": 0,
              "name": "nbdkit-debuginfo",
              "release": "4.module+el8.3.0+6922+fd575af8",
              "repositories": [
                {
                  "arch": "x86_64",
                  "name": "almalinux-8-appstream-debuginfo"
                }
              ],
              "version": "1.16.2"
            },
            {
              "arch": "x86_64",
              "epoch": 0,
              "name": "nbdkit-debugsource",
              "release": "4.module+el8.3.0+6922+fd575af8",
              "repositories": [
                {
                  "arch": "x86_64",
                  "name": "almalinux-8-appstream-debuginfo"
                }
              ],
              "version": "1.16.2"
            },
            {
              "arch": "x86_64",
              "epoch": 0,
              "name": "nbdkit-devel",
              "release": "4.module+el8.3.0+6922+fd575af8",
              "repositories": [
                {
                  "arch": "x86_64",
                  "name": "almalinux-8-appstream"
                }
              ],
              "version": "1.16.2"
            },
            {
              "arch": "x86_64",
              "epoch": 0,
              "name": "nbdkit-example-plugins",
              "release": "4.module+el8.3.0+6922+fd575af8",
              "repositories": [
                {
                  "arch": "x86_64",
                  "name": "almalinux-8-appstream"
                }
              ],
              "version": "1.16.2"
            },
            {
              "arch": "x86_64",
              "epoch": 0,
              "name": "nbdkit-example-plugins-debuginfo",
              "release": "4.module+el8.3.0+6922+fd575af8",
              "repositories": [
                {
                  "arch": "x86_64",
                  "name": "almalinux-8-appstream-debuginfo"
                }
              ],
              "version": "1.16.2"
            },
            {
              "arch": "x86_64",
              "epoch": 0,
              "name": "nbdkit-gzip-filter",
              "release": "4.module+el8.3.0+6922+fd575af8",
              "repositories": [
                {
                  "arch": "x86_64",
                  "name": "almalinux-8-appstream"
                }
              ],
              "version": "1.16.2"
            },
            {
              "arch": "x86_64",
              "epoch": 0,
              "name": "nbdkit-gzip-filter-debuginfo",
              "release": "4.module+el8.3.0+6922+fd575af8",
              "repositories": [
                {
                  "arch": "x86_64",
                  "name": "almalinux-8-appstream-debuginfo"
                }
              ],
              "version": "1.16.2"
            },
            {
              "arch": "x86_64",
              "epoch": 0,
              "name": "nbdkit-gzip-plugin",
              "release": "4.module+el8.3.0+6922+fd575af8",
              "repositories": [
                {
                  "arch": "x86_64",
                  "name": "almalinux-8-appstream"
                }
              ],
              "version": "1.16.2"
            },
            {
              "arch": "x86_64",
              "epoch": 0,
              "name": "nbdkit-gzip-plugin-debuginfo",
              "release": "4.module+el8.3.0+6922+fd575af8",
              "repositories": [
                {
                  "arch": "x86_64",
                  "name": "almalinux-8-appstream-debuginfo"
                }
              ],
              "version": "1.16.2"
            },
            {
              "arch": "x86_64",
              "epoch": 0,
              "name": "nbdkit-linuxdisk-plugin",
              "release": "4.module+el8.3.0+6922+fd575af8",
              "repositories": [
                {
                  "arch": "x86_64",
                  "name": "almalinux-8-appstream"
                }
              ],
              "version": "1.16.2"
            },
            {
              "arch": "x86_64",
              "epoch": 0,
              "name": "nbdkit-linuxdisk-plugin-debuginfo",
              "release": "4.module+el8.3.0+6922+fd575af8",
              "repositories": [
                {
                  "arch": "x86_64",
                  "name": "almalinux-8-appstream-debuginfo"
                }
              ],
              "version": "1.16.2"
            },
            {
              "arch": "x86_64",
              "epoch": 0,
              "name": "nbdkit-nbd-plugin",
              "release": "4.module+el8.3.0+6922+fd575af8",
              "repositories": [
                {
                  "arch": "x86_64",
                  "name": "almalinux-8-appstream"
                }
              ],
              "version": "1.16.2"
            },
            {
              "arch": "x86_64",
              "epoch": 0,
              "name": "nbdkit-nbd-plugin-debuginfo",
              "release": "4.module+el8.3.0+6922+fd575af8",
              "repositories": [
                {
                  "arch": "x86_64",
                  "name": "almalinux-8-appstream-debuginfo"
                }
              ],
              "version": "1.16.2"
            },
            {
              "arch": "x86_64",
              "epoch": 0,
              "name": "nbdkit-python-plugin",
              "release": "4.module+el8.3.0+6922+fd575af8",
              "repositories": [
                {
                  "arch": "x86_64",
                  "name": "almalinux-8-appstream"
                }
              ],
              "version": "1.16.2"
            },
            {
              "arch": "x86_64",
              "epoch": 0,
              "name": "nbdkit-python-plugin-debuginfo",
              "release": "4.module+el8.3.0+6922+fd575af8",
              "repositories": [
                {
                  "arch": "x86_64",
                  "name": "almalinux-8-appstream-debuginfo"
                }
              ],
              "version": "1.16.2"
            },
            {
              "arch": "x86_64",
              "epoch": 0,
              "name": "nbdkit-server",
              "release": "4.module+el8.3.0+6922+fd575af8",
              "repositories": [
                {
                  "arch": "x86_64",
                  "name": "almalinux-8-appstream"
                }
              ],
              "version": "1.16.2"
            },
            {
              "arch": "x86_64",
              "epoch": 0,
              "name": "nbdkit-server-debuginfo",
              "release": "4.module+el8.3.0+6922+fd575af8",
              "repositories": [
                {
                  "arch": "x86_64",
                  "name": "almalinux-8-appstream-debuginfo"
                }
              ],
              "version": "1.16.2"
            },
            {
              "arch": "x86_64",
              "epoch": 0,
              "name": "nbdkit-ssh-plugin",
              "release": "4.module+el8.3.0+6922+fd575af8",
              "repositories": [
                {
                  "arch": "x86_64",
                  "name": "almalinux-8-appstream"
                }
              ],
              "version": "1.16.2"
            },
            {
              "arch": "x86_64",
              "epoch": 0,
              "name": "nbdkit-ssh-plugin-debuginfo",
              "release": "4.module+el8.3.0+6922+fd575af8",
              "repositories": [
                {
                  "arch": "x86_64",
                  "name": "almalinux-8-appstream-debuginfo"
                }
              ],
              "version": "1.16.2"
            },
            {
              "arch": "x86_64",
              "epoch": 0,
              "name": "nbdkit-tar-filter",
              "release": "4.module+el8.3.0+6922+fd575af8",
              "repositories": [
                {
                  "arch": "x86_64",
                  "name": "almalinux-8-appstream"
                }
              ],
              "version": "1.16.2"
            },
            {
              "arch": "x86_64",
              "epoch": 0,
              "name": "nbdkit-tar-filter-debuginfo",
              "release": "4.module+el8.3.0+6922+fd575af8",
              "repositories": [
                {
                  "arch": "x86_64",
                  "name": "almalinux-8-appstream-debuginfo"
                }
              ],
              "version": "1.16.2"
            },
            {
              "arch": "x86_64",
              "epoch": 0,
              "name": "nbdkit-tar-plugin",
              "release": "4.module+el8.3.0+6922+fd575af8",
              "repositories": [
                {
                  "arch": "x86_64",
                  "name": "almalinux-8-appstream"
                }
              ],
              "version": "1.16.2"
            },
            {
              "arch": "x86_64",
              "epoch": 0,
              "name": "nbdkit-tar-plugin-debuginfo",
              "release": "4.module+el8.3.0+6922+fd575af8",
              "repositories": [
                {
                  "arch": "x86_64",
                  "name": "almalinux-8-appstream-debuginfo"
                }
              ],
              "version": "1.16.2"
            },
            {
              "arch": "x86_64",
              "epoch": 0,
              "name": "nbdkit-tmpdisk-plugin",
              "release": "4.module+el8.3.0+6922+fd575af8",
              "repositories": [
                {
                  "arch": "x86_64",
                  "name": "almalinux-8-appstream"
                }
              ],
              "version": "1.16.2"
            },
            {
              "arch": "x86_64",
              "epoch": 0,
              "name": "nbdkit-tmpdisk-plugin-debuginfo",
              "release": "4.module+el8.3.0+6922+fd575af8",
              "repositories": [
                {
                  "arch": "x86_64",
                  "name": "almalinux-8-appstream-debuginfo"
                }
              ],
              "version": "1.16.2"
            },
            {
              "arch": "x86_64",
              "epoch": 0,
              "name": "nbdkit-vddk-plugin",
              "release": "4.module+el8.3.0+6922+fd575af8",
              "repositories": [
                {
                  "arch": "x86_64",
                  "name": "almalinux-8-appstream"
                }
              ],
              "version": "1.16.2"
            },
            {
              "arch": "x86_64",
              "epoch": 0,
              "name": "nbdkit-vddk-plugin-debuginfo",
              "release": "4.module+el8.3.0+6922+fd575af8",
              "repositories": [
                {
                  "arch": "x86_64",
                  "name": "almalinux-8-appstream-debuginfo"
                }
              ],
              "version": "1.16.2"
            },
            {
              "arch": "x86_64",
              "epoch": 0,
              "name": "nbdkit-xz-filter",
              "release": "4.module+el8.3.0+6922+fd575af8",
              "repositories": [
                {
                  "arch": "x86_64",
                  "name": "almalinux-8-appstream"
                }
              ],
              "version": "1.16.2"
            },
            {
              "arch": "x86_64",
              "epoch": 0,
              "name": "nbdkit-xz-filter-debuginfo",
              "release": "4.module+el8.3.0+6922+fd575af8",
              "repositories": [
                {
                  "arch": "x86_64",
                  "name": "almalinux-8-appstream-debuginfo"
                }
              ],
              "version": "1.16.2"
            }
          ],
          "sourcerpm": {
            "epoch": 0,
            "name": "nbdkit",
            "release": "4.module+el8.3.0+6922+fd575af8",
            "version": "1.16.2"
          }
        },
        {
          "packages": [
            {
              "arch": "src",
              "epoch": 0,
              "name": "netcf",
              "release": "12.module+el8.1.0+4066+0f1aadab",
              "repositories": [
                {
                  "arch": "src",
                  "name": "almalinux-8-appstream"
                }
              ],
              "version": "0.2.8"
            },
            {
              "arch": "x86_64",
              "epoch": 0,
              "name": "netcf",
              "release": "12.module+el8.1.0+4066+0f1aadab",
              "repositories": [
                {
                  "arch": "x86_64",
                  "name": "almalinux-8-appstream"
                }
              ],
              "version": "0.2.8"
            },
            {
              "arch": "x86_64",
              "epoch": 0,
              "name": "netcf-debuginfo",
              "release": "12.module+el8.1.0+4066+0f1aadab",
              "repositories": [
                {
                  "arch": "x86_64",
                  "name": "almalinux-8-appstream-debuginfo"
                }
              ],
              "version": "0.2.8"
            },
            {
              "arch": "x86_64",
              "epoch": 0,
              "name": "netcf-debugsource",
              "release": "12.module+el8.1.0+4066+0f1aadab",
              "repositories": [
                {
                  "arch": "x86_64",
                  "name": "almalinux-8-appstream-debuginfo"
                }
              ],
              "version": "0.2.8"
            },
            {
              "arch": "x86_64",
              "epoch": 0,
              "name": "netcf-devel",
              "release": "12.module+el8.1.0+4066+0f1aadab",
              "repositories": [
                {
                  "arch": "x86_64",
                  "name": "almalinux-8-appstream"
                }
              ],
              "version": "0.2.8"
            },
            {
              "arch": "x86_64",
              "epoch": 0,
              "name": "netcf-libs",
              "release": "12.module+el8.1.0+4066+0f1aadab",
              "repositories": [
                {
                  "arch": "x86_64",
                  "name": "almalinux-8-appstream"
                }
              ],
              "version": "0.2.8"
            },
            {
              "arch": "x86_64",
              "epoch": 0,
              "name": "netcf-libs-debuginfo",
              "release": "12.module+el8.1.0+4066+0f1aadab",
              "repositories": [
                {
                  "arch": "x86_64",
                  "name": "almalinux-8-appstream-debuginfo"
                }
              ],
              "version": "0.2.8"
            }
          ],
          "sourcerpm": {
            "epoch": 0,
            "name": "netcf",
            "release": "12.module+el8.1.0+4066+0f1aadab",
            "version": "0.2.8"
          }
        },
        {
          "packages": [
            {
              "arch": "src",
              "epoch": 0,
              "name": "perl-Sys-Virt",
              "release": "1.module+el8.3.0+6423+e4cb6418",
              "repositories": [
                {
                  "arch": "src",
                  "name": "almalinux-8-appstream"
                }
              ],
              "version": "6.0.0"
            },
            {
              "arch": "x86_64",
              "epoch": 0,
              "name": "perl-Sys-Virt",
              "release": "1.module+el8.3.0+6423+e4cb6418",
              "repositories": [
                {
                  "arch": "x86_64",
                  "name": "almalinux-8-appstream"
                }
              ],
              "version": "6.0.0"
            },
            {
              "arch": "x86_64",
              "epoch": 0,
              "name": "perl-Sys-Virt-debuginfo",
              "release": "1.module+el8.3.0+6423+e4cb6418",
              "repositories": [
                {
                  "arch": "x86_64",
                  "name": "almalinux-8-appstream-debuginfo"
                }
              ],
              "version": "6.0.0"
            },
            {
              "arch": "x86_64",
              "epoch": 0,
              "name": "perl-Sys-Virt-debugsource",
              "release": "1.module+el8.3.0+6423+e4cb6418",
              "repositories": [
                {
                  "arch": "x86_64",
                  "name": "almalinux-8-appstream-debuginfo"
                }
              ],
              "version": "6.0.0"
            }
          ],
          "sourcerpm": {
            "epoch": 0,
            "name": "perl-Sys-Virt",
            "release": "1.module+el8.3.0+6423+e4cb6418",
            "version": "6.0.0"
          }
        },
        {
          "packages": [
            {
              "arch": "x86_64",
              "epoch": 15,
              "name": "qemu-guest-agent",
              "release": "34.module+el8.3.0+9903+ca3e42fb.4",
              "repositories": [
                {
                  "arch": "x86_64",
                  "name": "almalinux-8-appstream"
                }
              ],
              "version": "4.2.0"
            },
            {
              "arch": "x86_64",
              "epoch": 15,
              "name": "qemu-guest-agent-debuginfo",
              "release": "34.module+el8.3.0+9903+ca3e42fb.4",
              "repositories": [
                {
                  "arch": "x86_64",
                  "name": "almalinux-8-appstream-debuginfo"
                }
              ],
              "version": "4.2.0"
            },
            {
              "arch": "x86_64",
              "epoch": 15,
              "name": "qemu-img",
              "release": "34.module+el8.3.0+9903+ca3e42fb.4",
              "repositories": [
                {
                  "arch": "x86_64",
                  "name": "almalinux-8-appstream"
                }
              ],
              "version": "4.2.0"
            },
            {
              "arch": "x86_64",
              "epoch": 15,
              "name": "qemu-img-debuginfo",
              "release": "34.module+el8.3.0+9903+ca3e42fb.4",
              "repositories": [
                {
                  "arch": "x86_64",
                  "name": "almalinux-8-appstream-debuginfo"
                }
              ],
              "version": "4.2.0"
            },
            {
              "arch": "src",
              "epoch": 15,
              "name": "qemu-kvm",
              "release": "34.module+el8.3.0+9903+ca3e42fb.4",
              "repositories": [
                {
                  "arch": "src",
                  "name": "almalinux-8-appstream"
                }
              ],
              "version": "4.2.0"
            },
            {
              "arch": "x86_64",
              "epoch": 15,
              "name": "qemu-kvm",
              "release": "34.module+el8.3.0+9903+ca3e42fb.4",
              "repositories": [
                {
                  "arch": "x86_64",
                  "name": "almalinux-8-appstream"
                }
              ],
              "version": "4.2.0"
            },
            {
              "arch": "x86_64",
              "epoch": 15,
              "name": "qemu-kvm-block-curl",
              "release": "34.module+el8.3.0+9903+ca3e42fb.4",
              "repositories": [
                {
                  "arch": "x86_64",
                  "name": "almalinux-8-appstream"
                }
              ],
              "version": "4.2.0"
            },
            {
              "arch": "x86_64",
              "epoch": 15,
              "name": "qemu-kvm-block-curl-debuginfo",
              "release": "34.module+el8.3.0+9903+ca3e42fb.4",
              "repositories": [
                {
                  "arch": "x86_64",
                  "name": "almalinux-8-appstream-debuginfo"
                }
              ],
              "version": "4.2.0"
            },
            {
              "arch": "x86_64",
              "epoch": 15,
              "name": "qemu-kvm-block-gluster",
              "release": "34.module+el8.3.0+9903+ca3e42fb.4",
              "repositories": [
                {
                  "arch": "x86_64",
                  "name": "almalinux-8-appstream"
                }
              ],
              "version": "4.2.0"
            },
            {
              "arch": "x86_64",
              "epoch": 15,
              "name": "qemu-kvm-block-gluster-debuginfo",
              "release": "34.module+el8.3.0+9903+ca3e42fb.4",
              "repositories": [
                {
                  "arch": "x86_64",
                  "name": "almalinux-8-appstream-debuginfo"
                }
              ],
              "version": "4.2.0"
            },
            {
              "arch": "x86_64",
              "epoch": 15,
              "name": "qemu-kvm-block-iscsi",
              "release": "34.module+el8.3.0+9903+ca3e42fb.4",
              "repositories": [
                {
                  "arch": "x86_64",
                  "name": "almalinux-8-appstream"
                }
              ],
              "version": "4.2.0"
            },
            {
              "arch": "x86_64",
              "epoch": 15,
              "name": "qemu-kvm-block-iscsi-debuginfo",
              "release": "34.module+el8.3.0+9903+ca3e42fb.4",
              "repositories": [
                {
                  "arch": "x86_64",
                  "name": "almalinux-8-appstream-debuginfo"
                }
              ],
              "version": "4.2.0"
            },
            {
              "arch": "x86_64",
              "epoch": 15,
              "name": "qemu-kvm-block-rbd",
              "release": "34.module+el8.3.0+9903+ca3e42fb.4",
              "repositories": [
                {
                  "arch": "x86_64",
                  "name": "almalinux-8-appstream"
                }
              ],
              "version": "4.2.0"
            },
            {
              "arch": "x86_64",
              "epoch": 15,
              "name": "qemu-kvm-block-rbd-debuginfo",
              "release": "34.module+el8.3.0+9903+ca3e42fb.4",
              "repositories": [
                {
                  "arch": "x86_64",
                  "name": "almalinux-8-appstream-debuginfo"
                }
              ],
              "version": "4.2.0"
            },
            {
              "arch": "x86_64",
              "epoch": 15,
              "name": "qemu-kvm-block-ssh",
              "release": "34.module+el8.3.0+9903+ca3e42fb.4",
              "repositories": [
                {
                  "arch": "x86_64",
                  "name": "almalinux-8-appstream"
                }
              ],
              "version": "4.2.0"
            },
            {
              "arch": "x86_64",
              "epoch": 15,
              "name": "qemu-kvm-block-ssh-debuginfo",
              "release": "34.module+el8.3.0+9903+ca3e42fb.4",
              "repositories": [
                {
                  "arch": "x86_64",
                  "name": "almalinux-8-appstream-debuginfo"
                }
              ],
              "version": "4.2.0"
            },
            {
              "arch": "x86_64",
              "epoch": 15,
              "name": "qemu-kvm-common",
              "release": "34.module+el8.3.0+9903+ca3e42fb.4",
              "repositories": [
                {
                  "arch": "x86_64",
                  "name": "almalinux-8-appstream"
                }
              ],
              "version": "4.2.0"
            },
            {
              "arch": "x86_64",
              "epoch": 15,
              "name": "qemu-kvm-common-debuginfo",
              "release": "34.module+el8.3.0+9903+ca3e42fb.4",
              "repositories": [
                {
                  "arch": "x86_64",
                  "name": "almalinux-8-appstream-debuginfo"
                }
              ],
              "version": "4.2.0"
            },
            {
              "arch": "x86_64",
              "epoch": 15,
              "name": "qemu-kvm-core",
              "release": "34.module+el8.3.0+9903+ca3e42fb.4",
              "repositories": [
                {
                  "arch": "x86_64",
                  "name": "almalinux-8-appstream"
                }
              ],
              "version": "4.2.0"
            },
            {
              "arch": "x86_64",
              "epoch": 15,
              "name": "qemu-kvm-core-debuginfo",
              "release": "34.module+el8.3.0+9903+ca3e42fb.4",
              "repositories": [
                {
                  "arch": "x86_64",
                  "name": "almalinux-8-appstream-debuginfo"
                }
              ],
              "version": "4.2.0"
            },
            {
              "arch": "x86_64",
              "epoch": 15,
              "name": "qemu-kvm-debuginfo",
              "release": "34.module+el8.3.0+9903+ca3e42fb.4",
              "repositories": [
                {
                  "arch": "x86_64",
                  "name": "almalinux-8-appstream-debuginfo"
                }
              ],
              "version": "4.2.0"
            },
            {
              "arch": "x86_64",
              "epoch": 15,
              "name": "qemu-kvm-debugsource",
              "release": "34.module+el8.3.0+9903+ca3e42fb.4",
              "repositories": [
                {
                  "arch": "x86_64",
                  "name": "almalinux-8-appstream-debuginfo"
                }
              ],
              "version": "4.2.0"
            },
            {
              "arch": "x86_64",
              "epoch": 15,
              "name": "qemu-kvm-docs",
              "release": "34.module+el8.3.0+9903+ca3e42fb.4",
              "repositories": [
                {
                  "arch": "x86_64",
                  "name": "almalinux-8-appstream"
                }
              ],
              "version": "4.2.0"
            },
            {
              "arch": "x86_64",
              "epoch": 15,
              "name": "qemu-kvm-hw-usbredir",
              "release": "34.module+el8.3.0+9903+ca3e42fb.4",
              "repositories": [
                {
                  "arch": "x86_64",
                  "name": "almalinux-8-appstream"
                }
              ],
              "version": "4.2.0"
            },
            {
              "arch": "x86_64",
              "epoch": 15,
              "name": "qemu-kvm-hw-usbredir-debuginfo",
              "release": "34.module+el8.3.0+9903+ca3e42fb.4",
              "repositories": [
                {
                  "arch": "x86_64",
                  "name": "almalinux-8-appstream-debuginfo"
                }
              ],
              "version": "4.2.0"
            },
            {
              "arch": "x86_64",
              "epoch": 15,
              "name": "qemu-kvm-ui-opengl",
              "release": "34.module+el8.3.0+9903+ca3e42fb.4",
              "repositories": [
                {
                  "arch": "x86_64",
                  "name": "almalinux-8-appstream"
                }
              ],
              "version": "4.2.0"
            },
            {
              "arch": "x86_64",
              "epoch": 15,
              "name": "qemu-kvm-ui-opengl-debuginfo",
              "release": "34.module+el8.3.0+9903+ca3e42fb.4",
              "repositories": [
                {
                  "arch": "x86_64",
                  "name": "almalinux-8-appstream-debuginfo"
                }
              ],
              "version": "4.2.0"
            },
            {
              "arch": "x86_64",
              "epoch": 15,
              "name": "qemu-kvm-ui-spice",
              "release": "34.module+el8.3.0+9903+ca3e42fb.4",
              "repositories": [
                {
                  "arch": "x86_64",
                  "name": "almalinux-8-appstream"
                }
              ],
              "version": "4.2.0"
            },
            {
              "arch": "x86_64",
              "epoch": 15,
              "name": "qemu-kvm-ui-spice-debuginfo",
              "release": "34.module+el8.3.0+9903+ca3e42fb.4",
              "repositories": [
                {
                  "arch": "x86_64",
                  "name": "almalinux-8-appstream-debuginfo"
                }
              ],
              "version": "4.2.0"
            }
          ],
          "sourcerpm": {
            "epoch": 15,
            "name": "qemu-kvm",
            "release": "34.module+el8.3.0+9903+ca3e42fb.4",
            "version": "4.2.0"
          }
        },
        {
          "packages": [
            {
              "arch": "src",
              "epoch": 0,
              "name": "seabios",
              "release": "2.module+el8.3.0+7353+9de0a3cc",
              "repositories": [
                {
                  "arch": "src",
                  "name": "almalinux-8-appstream"
                }
              ],
              "version": "1.13.0"
            },
            {
              "arch": "x86_64",
              "epoch": 0,
              "name": "seabios",
              "release": "2.module+el8.3.0+7353+9de0a3cc",
              "repositories": [
                {
                  "arch": "x86_64",
                  "name": "almalinux-8-appstream"
                }
              ],
              "version": "1.13.0"
            },
            {
              "arch": "noarch",
              "epoch": 0,
              "name": "seabios-bin",
              "release": "2.module+el8.3.0+7353+9de0a3cc",
              "repositories": [
                {
                  "arch": "x86_64",
                  "name": "almalinux-8-appstream"
                }
              ],
              "version": "1.13.0"
            },
            {
              "arch": "noarch",
              "epoch": 0,
              "name": "seavgabios-bin",
              "release": "2.module+el8.3.0+7353+9de0a3cc",
              "repositories": [
                {
                  "arch": "x86_64",
                  "name": "almalinux-8-appstream"
                }
              ],
              "version": "1.13.0"
            }
          ],
          "sourcerpm": {
            "epoch": 0,
            "name": "seabios",
            "release": "2.module+el8.3.0+7353+9de0a3cc",
            "version": "1.13.0"
          }
        },
        {
          "packages": [
            {
              "arch": "src",
              "epoch": 1,
              "name": "sgabios",
              "release": "3.module+el8.1.0+4066+0f1aadab",
              "repositories": [
                {
                  "arch": "src",
                  "name": "almalinux-8-appstream"
                }
              ],
              "version": "0.20170427git"
            },
            {
              "arch": "x86_64",
              "epoch": 1,
              "name": "sgabios",
              "release": "3.module+el8.1.0+4066+0f1aadab",
              "repositories": [
                {
                  "arch": "x86_64",
                  "name": "almalinux-8-appstream"
                }
              ],
              "version": "0.20170427git"
            },
            {
              "arch": "noarch",
              "epoch": 1,
              "name": "sgabios-bin",
              "release": "3.module+el8.1.0+4066+0f1aadab",
              "repositories": [
                {
                  "arch": "x86_64",
                  "name": "almalinux-8-appstream"
                }
              ],
              "version": "0.20170427git"
            }
          ],
          "sourcerpm": {
            "epoch": 1,
            "name": "sgabios",
            "release": "3.module+el8.1.0+4066+0f1aadab",
            "version": "0.20170427git"
          }
        },
        {
          "packages": [
            {
              "arch": "src",
              "epoch": 0,
              "name": "supermin",
              "release": "2.module+el8.3.0+6423+e4cb6418",
              "repositories": [
                {
                  "arch": "src",
                  "name": "almalinux-8-appstream"
                }
              ],
              "version": "5.1.19"
            },
            {
              "arch": "x86_64",
              "epoch": 0,
              "name": "supermin",
              "release": "10.module+el8.3.0+6423+e4cb6418",
              "repositories": [
                {
                  "arch": "x86_64",
                  "name": "almalinux-8-appstream"
                }
              ],
              "version": "5.1.19"
            },
            {
              "arch": "x86_64",
              "epoch": 0,
              "name": "supermin-debuginfo",
              "release": "10.module+el8.3.0+6423+e4cb6418",
              "repositories": [
                {
                  "arch": "x86_64",
                  "name": "almalinux-8-appstream-debuginfo"
                }
              ],
              "version": "5.1.19"
            },
            {
              "arch": "x86_64",
              "epoch": 0,
              "name": "supermin-debugsource",
              "release": "10.module+el8.3.0+6423+e4cb6418",
              "repositories": [
                {
                  "arch": "x86_64",
                  "name": "almalinux-8-appstream-debuginfo"
                }
              ],
              "version": "5.1.19"
            },
            {
              "arch": "x86_64",
              "epoch": 0,
              "name": "supermin-devel",
              "release": "10.module+el8.3.0+6423+e4cb6418",
              "repositories": [
                {
                  "arch": "x86_64",
                  "name": "almalinux-8-appstream"
                }
              ],
              "version": "5.1.19"
            }
          ],
          "sourcerpm": {
            "epoch": 0,
            "name": "supermin",
            "release": "10.module+el8.3.0+6423+e4cb6418",
            "version": "5.1.19"
          }
        },
        {
          "packages": [
            {
              "arch": "src",
              "epoch": 1,
              "name": "virt-v2v",
              "release": "25.module+el8.3.0+7421+642fe24f",
              "repositories": [
                {
                  "arch": "src",
                  "name": "almalinux-8-appstream"
                }
              ],
              "version": "1.40.2"
            },
            {
              "arch": "x86_64",
              "epoch": 1,
              "name": "virt-v2v",
              "release": "25.module+el8.3.0+7421+642fe24f",
              "repositories": [
                {
                  "arch": "x86_64",
                  "name": "almalinux-8-appstream"
                }
              ],
              "version": "1.40.2"
            },
            {
              "arch": "noarch",
              "epoch": 1,
              "name": "virt-v2v-bash-completion",
              "release": "25.module+el8.3.0+7421+642fe24f",
              "repositories": [
                {
                  "arch": "x86_64",
                  "name": "almalinux-8-appstream"
                }
              ],
              "version": "1.40.2"
            },
            {
              "arch": "x86_64",
              "epoch": 1,
              "name": "virt-v2v-debuginfo",
              "release": "25.module+el8.3.0+7421+642fe24f",
              "repositories": [
                {
                  "arch": "x86_64",
                  "name": "almalinux-8-appstream-debuginfo"
                }
              ],
              "version": "1.40.2"
            },
            {
              "arch": "x86_64",
              "epoch": 1,
              "name": "virt-v2v-debugsource",
              "release": "25.module+el8.3.0+7421+642fe24f",
              "repositories": [
                {
                  "arch": "x86_64",
                  "name": "almalinux-8-appstream-debuginfo"
                }
              ],
              "version": "1.40.2"
            },
            {
              "arch": "noarch",
              "epoch": 1,
              "name": "virt-v2v-man-pages-ja",
              "release": "25.module+el8.3.0+7421+642fe24f",
              "repositories": [
                {
                  "arch": "x86_64",
                  "name": "almalinux-8-appstream"
                }
              ],
              "version": "1.40.2"
            },
            {
              "arch": "noarch",
              "epoch": 1,
              "name": "virt-v2v-man-pages-uk",
              "release": "25.module+el8.3.0+7421+642fe24f",
              "repositories": [
                {
                  "arch": "x86_64",
                  "name": "almalinux-8-appstream"
                }
              ],
              "version": "1.40.2"
            }
          ],
          "sourcerpm": {
            "epoch": 1,
            "name": "virt-v2v",
            "release": "25.module+el8.3.0+7421+642fe24f",
            "version": "1.40.2"
          }
        }
      ],
      "context": "bd1311ed",
      "name": "virt",
      "repository": {
        "arch": "x86_64",
        "name": "almalinux-8-appstream"
      },
      "stream": "rhel",
      "type": "module",
      "version": 8030020210210212009
    },
    "/api/v1/distros/AlmaLinux/8/module/virt-devel/rhel/x86_64/": {
      "arch": "x86_64",
      "artifacts": [
        {
          "packages": [
            {
              "arch": "i686",
              "epoch": 0,
              "name": "hivex",
              "release": "20.module+el8.3.0+6423+e4cb6418",
              "repositories": [
                {
                  "arch": "x86_64",
                  "name": "almalinux-8-powertools"
                }
              ],
              "version": "1.3.18"
            },
            {
              "arch": "i686",
              "epoch": 0,
              "name": "hivex-debuginfo",
              "release": "20.module+el8.3.0+6423+e4cb6418",
              "repositories": [
                {
                  "arch": "x86_64",
                  "name": "almalinux-8-powertools-debuginfo"
                }
              ],
              "version": "1.3.18"
            },
            {
              "arch": "i686",
              "epoch": 0,
              "name": "hivex-debugsource",
              "release": "20.module+el8.3.0+6423+e4cb6418",
              "repositories": [
                {
                  "arch": "x86_64",
                  "name": "almalinux-8-powertools-debuginfo"
                }
              ],
              "version": "1.3.18"
            },
            {
              "arch": "i686",
              "epoch": 0,
              "name": "hivex-devel",
              "release": "20.module+el8.3.0+6423+e4cb6418",
              "repositories": [
                {
                  "arch": "x86_64",
                  "name": "almalinux-8-powertools"
                }
              ],
              "version": "1.3.18"
            },
            {
              "arch": "i686",
              "epoch": 0,
              "name": "ocaml-hivex",
              "release": "20.module+el8.3.0+6423+e4cb6418",
              "repositories": [
                {
                  "arch": "x86_64",
                  "name": "almalinux-8-powertools"
                }
              ],
              "version": "1.3.18"
            },
            {
              "arch": "x86_64",
              "epoch": 0,
              "name": "ocaml-hivex",
              "release": "20.module+el8.3.0+6423+e4cb6418",
              "repositories": [
                {
                  "arch": "x86_64",
                  "name": "almalinux-8-powertools"
                }
              ],
              "version": "1.3.18"
            },
            {
              "arch": "i686",
              "epoch": 0,
              "name": "ocaml-hivex-debuginfo",
              "release": "20.module+el8.3.0+6423+e4cb6418",
              "repositories": [
                {
                  "arch": "x86_64",
                  "name": "almalinux-8-powertools-debuginfo"
                }
              ],
              "version": "1.3.18"
            },
            {
              "arch": "x86_64",
              "epoch": 0,
              "name": "ocaml-hivex-debuginfo",
              "release": "20.module+el8.3.0+6423+e4cb6418",
              "repositories": [
                {
                  "arch": "x86_64",
                  "name": "almalinux-8-powertools-debuginfo"
                }
              ],
              "version": "1.3.18"
            },
            {
              "arch": "i686",
              "epoch": 0,
              "name": "ocaml-hivex-devel",
              "release": "20.module+el8.3.0+6423+e4cb6418",
              "repositories": [
                {
                  "arch": "x86_64",
                  "name": "almalinux-8-powertools"
                }
              ],
              "version": "1.3.18"
            },
            {
              "arch": "x86_64",
              "epoch": 0,
              "name": "ocaml-hivex-devel",
              "release": "20.module+el8.3.0+6423+e4cb6418",
              "repositories": [
                {
                  "arch": "x86_64",
                  "name": "almalinux-8-powertools"
                }
              ],
              "version": "1.3.18"
            },
            {
              "arch": "i686",
              "epoch": 0,
              "name": "perl-hivex",
              "release": "20.module+el8.3.0+6423+e4cb6418",
              "repositories": [
                {
                  "arch": "x86_64",
                  "name": "almalinux-8-powertools"
                }
              ],
              "version": "1.3.18"
            },
            {
              "arch": "i686",
              "epoch": 0,
              "name": "perl-hivex-debuginfo",
              "release": "20.module+el8.3.0+6423+e4cb6418",
              "repositories": [
                {
                  "arch": "x86_64",
                  "name": "almalinux-8-powertools-debuginfo"
                }
              ],
              "version": "1.3.18"
            },
            {
              "arch": "i686",
              "epoch": 0,
              "name": "python3-hivex",
              "release": "20.module+el8.3.0+6423+e4cb6418",
              "repositories": [
                {
                  "arch": "x86_64",
                  "name": "almalinux-8-powertools"
                }
              ],
              "version": "1.3.18"
            },
            {
              "arch": "i686",
              "epoch": 0,
              "name": "python3-hivex-debuginfo",
              "release": "20.module+el8.3.0+6423+e4cb6418",
              "repositories": [
                {
                  "arch": "x86_64",
                  "name": "almalinux-8-powertools-debuginfo"
                }
              ],
              "version": "1.3.18"
            },
            {
              "arch": "i686",
              "epoch": 0,
              "name": "ruby-hivex",
              "release": "20.module+el8.3.0+6423+e4cb6418",
              "repositories": [
                {
                  "arch": "x86_64",
                  "name": "almalinux-8-powertools"
                }
              ],
              "version": "1.3.18"
            },
            {
              "arch": "i686",
              "epoch": 0,
              "name": "ruby-hivex-debuginfo",
              "release": "20.module+el8.3.0+6423+e4cb6418",
              "repositories": [
                {
                  "arch": "x86_64",
                  "name": "almalinux-8-powertools-debuginfo"
                }
              ],
              "version": "1.3.18"
            }
          ],
          "sourcerpm": {
            "name": "hivex",
            "release": "20.module+el8.3.0+6423+e4cb6418",
            "version": "1.3.18"
          }
        },
        {
          "packages": [
            {
              "arch": "i686",
              "epoch": 0,
              "name": "libguestfs-winsupport",
              "release": "1.module+el8.3.0+6423+e4cb6418",
              "repositories": [
                {
                  "arch": "x86_64",
                  "name": "almalinux-8-powertools"
                }
              ],
              "version": "8.2"
            }
          ],
          "sourcerpm": {
            "name": "libguestfs-winsupport",
            "release": "1.module+el8.3.0+6423+e4cb6418",
            "version": "8.2"
          }
        },
        {
          "packages": [
            {
              "arch": "i686",
              "epoch": 0,
              "name": "libiscsi",
              "release": "8.module+el8.1.0+4066+0f1aadab",
              "repositories": [
                {
                  "arch": "x86_64",
                  "name": "almalinux-8-powertools"
                }
              ],
              "version": "1.18.0"
            },
            {
              "arch": "i686",
              "epoch": 0,
              "name": "libiscsi-debuginfo",
              "release": "8.module+el8.1.0+4066+0f1aadab",
              "repositories": [
                {
                  "arch": "x86_64",
                  "name": "almalinux-8-powertools-debuginfo"
                }
              ],
              "version": "1.18.0"
            },
            {
              "arch": "i686",
              "epoch": 0,
              "name": "libiscsi-debugsource",
              "release": "8.module+el8.1.0+4066+0f1aadab",
              "repositories": [
                {
                  "arch": "x86_64",
                  "name": "almalinux-8-powertools-debuginfo"
                }
              ],
              "version": "1.18.0"
            },
            {
              "arch": "i686",
              "epoch": 0,
              "name": "libiscsi-devel",
              "release": "8.module+el8.1.0+4066+0f1aadab",
              "repositories": [
                {
                  "arch": "x86_64",
                  "name": "almalinux-8-powertools"
                }
              ],
              "version": "1.18.0"
            },
            {
              "arch": "i686",
              "epoch": 0,
              "name": "libiscsi-utils",
              "release": "8.module+el8.1.0+4066+0f1aadab",
              "repositories": [
                {
                  "arch": "x86_64",
                  "name": "almalinux-8-powertools"
                }
              ],
              "version": "1.18.0"
            },
            {
              "arch": "i686",
              "epoch": 0,
              "name": "libiscsi-utils-debuginfo",
              "release": "8.module+el8.1.0+4066+0f1aadab",
              "repositories": [
                {
                  "arch": "x86_64",
                  "name": "almalinux-8-powertools-debuginfo"
                }
              ],
              "version": "1.18.0"
            }
          ],
          "sourcerpm": {
            "name": "libiscsi",
            "release": "8.module+el8.1.0+4066+0f1aadab",
            "version": "1.18.0"
          }
        },
        {
          "packages": [
            {
              "arch": "i686",
              "epoch": 0,
              "name": "libnbd",
              "release": "1.module+el8.3.0+7353+9de0a3cc",
              "repositories": [
                {
                  "arch": "x86_64",
                  "name": "almalinux-8-powertools"
                }
              ],
              "version": "1.2.2"
            },
            {
              "arch": "i686",
              "epoch": 0,
              "name": "libnbd-debuginfo",
              "release": "1.module+el8.3.0+7353+9de0a3cc",
              "repositories": [
                {
                  "arch": "x86_64",
                  "name": "almalinux-8-powertools-debuginfo"
                }
              ],
              "version": "1.2.2"
            },
            {
              "arch": "i686",
              "epoch": 0,
              "name": "libnbd-debugsource",
              "release": "1.module+el8.3.0+7353+9de0a3cc",
              "repositories": [
                {
                  "arch": "x86_64",
                  "name": "almalinux-8-powertools-debuginfo"
                }
              ],
              "version": "1.2.2"
            },
            {
              "arch": "i686",
              "epoch": 0,
              "name": "libnbd-devel",
              "release": "1.module+el8.3.0+7353+9de0a3cc",
              "repositories": [
                {
                  "arch": "x86_64",
                  "name": "almalinux-8-powertools"
                }
              ],
              "version": "1.2.2"
            },
            {
              "arch": "i686",
              "epoch": 0,
              "name": "nbdfuse",
              "release": "1.module+el8.3.0+7353+9de0a3cc",
              "repositories": [
                {
                  "arch": "x86_64",
                  "name": "almalinux-8-powertools"
                }
              ],
              "version": "1.2.2"
            },
            {
              "arch": "i686",
              "epoch": 0,
              "name": "nbdfuse-debuginfo",
              "release": "1.module+el8.3.0+7353+9de0a3cc",
              "repositories": [
                {
                  "arch": "x86_64",
                  "name": "almalinux-8-powertools-debuginfo"
                }
              ],
              "version": "1.2.2"
            },
            {
              "arch": "i686",
              "epoch": 0,
              "name": "ocaml-libnbd",
              "release": "1.module+el8.3.0+7353+9de0a3cc",
              "repositories": [
                {
                  "arch": "x86_64",
                  "name": "almalinux-8-powertools"
                }
              ],
              "version": "1.2.2"
            },
            {
              "arch": "x86_64",
              "epoch": 0,
              "name": "ocaml-libnbd",
              "release": "1.module+el8.3.0+7353+9de0a3cc",
              "repositories": [
                {
                  "arch": "x86_64",
                  "name": "almalinux-8-powertools"
                }
              ],
              "version": "1.2.2"
            },
            {
              "arch": "i686",
              "epoch": 0,
              "name": "ocaml-libnbd-debuginfo",
              "release": "1.module+el8.3.0+7353+9de0a3cc",
              "repositories": [
                {
                  "arch": "x86_64",
                  "name": "almalinux-8-powertools-debuginfo"
                }
              ],
              "version": "1.2.2"
            },
            {
              "arch": "x86_64",
              "epoch": 0,
              "name": "ocaml-libnbd-debuginfo",
              "release": "1.module+el8.3.0+7353+9de0a3cc",
              "repositories": [
                {
                  "arch": "x86_64",
                  "name": "almalinux-8-powertools-debuginfo"
                }
              ],
              "version": "1.2.2"
            },
            {
              "arch": "i686",
              "epoch": 0,
              "name": "ocaml-libnbd-devel",
              "release": "1.module+el8.3.0+7353+9de0a3cc",
              "repositories": [
                {
                  "arch": "x86_64",
                  "name": "almalinux-8-powertools"
                }
              ],
              "version": "1.2.2"
            },
            {
              "arch": "x86_64",
              "epoch": 0,
              "name": "ocaml-libnbd-devel",
              "release": "1.module+el8.3.0+7353+9de0a3cc",
              "repositories": [
                {
                  "arch": "x86_64",
                  "name": "almalinux-8-powertools"
                }
              ],
              "version": "1.2.2"
            },
            {
              "arch": "i686",
              "epoch": 0,
              "name": "python3-libnbd",
              "release": "1.module+el8.3.0+7353+9de0a3cc",
              "repositories": [
                {
                  "arch": "x86_64",
                  "name": "almalinux-8-powertools"
                }
              ],
              "version": "1.2.2"
            },
            {
              "arch": "i686",
              "epoch": 0,
              "name": "python3-libnbd-debuginfo",
              "release": "1.module+el8.3.0+7353+9de0a3cc",
              "repositories": [
                {
                  "arch": "x86_64",
                  "name": "almalinux-8-powertools-debuginfo"
                }
              ],
              "version": "1.2.2"
            }
          ],
          "sourcerpm": {
            "name": "libnbd",
            "release": "1.module+el8.3.0+7353+9de0a3cc",
            "version": "1.2.2"
          }
        },
        {
          "packages": [
            {
              "arch": "i686",
              "epoch": 0,
              "name": "libvirt",
              "release": "28.module+el8.3.0+7827+5e65edd7",
              "repositories": [
                {
                  "arch": "x86_64",
                  "name": "almalinux-8-powertools"
                }
              ],
              "version": "6.0.0"
            },
            {
              "arch": "i686",
              "epoch": 0,
              "name": "libvirt-client",
              "release": "28.module+el8.3.0+7827+5e65edd7",
              "repositories": [
                {
                  "arch": "x86_64",
                  "name": "almalinux-8-powertools"
                }
              ],
              "version": "6.0.0"
            },
            {
              "arch": "i686",
              "epoch": 0,
              "name": "libvirt-client-debuginfo",
              "release": "28.module+el8.3.0+7827+5e65edd7",
              "repositories": [
                {
                  "arch": "x86_64",
                  "name": "almalinux-8-powertools-debuginfo"
                }
              ],
              "version": "6.0.0"
            },
            {
              "arch": "i686",
              "epoch": 0,
              "name": "libvirt-daemon",
              "release": "28.module+el8.3.0+7827+5e65edd7",
              "repositories": [
                {
                  "arch": "x86_64",
                  "name": "almalinux-8-powertools"
                }
              ],
              "version": "6.0.0"
            },
            {
              "arch": "i686",
              "epoch": 0,
              "name": "libvirt-daemon-config-network",
              "release": "28.module+el8.3.0+7827+5e65edd7",
              "repositories": [
                {
                  "arch": "x86_64",
                  "name": "almalinux-8-powertools"
                }
              ],
              "version": "6.0.0"
            },
            {
              "arch": "i686",
              "epoch": 0,
              "name": "libvirt-daemon-config-nwfilter",
              "release": "28.module+el8.3.0+7827+5e65edd7",
              "repositories": [
                {
                  "arch": "x86_64",
                  "name": "almalinux-8-powertools"
                }
              ],
              "version": "6.0.0"
            },
            {
              "arch": "i686",
              "epoch": 0,
              "name": "libvirt-daemon-debuginfo",
              "release": "28.module+el8.3.0+7827+5e65edd7",
              "repositories": [
                {
                  "arch": "x86_64",
                  "name": "almalinux-8-powertools-debuginfo"
                }
              ],
              "version": "6.0.0"
            },
            {
              "arch": "i686",
              "epoch": 0,
              "name": "libvirt-daemon-driver-interface",
              "release": "28.module+el8.3.0+7827+5e65edd7",
              "repositories": [
                {
                  "arch": "x86_64",
                  "name": "almalinux-8-powertools"
                }
              ],
              "version": "6.0.0"
            },
            {
              "arch": "i686",
              "epoch": 0,
              "name": "libvirt-daemon-driver-interface-debuginfo",
              "release": "28.module+el8.3.0+7827+5e65edd7",
              "repositories": [
                {
                  "arch": "x86_64",
                  "name": "almalinux-8-powertools-debuginfo"
                }
              ],
              "version": "6.0.0"
            },
            {
              "arch": "i686",
              "epoch": 0,
              "name": "libvirt-daemon-driver-network",
              "release": "28.module+el8.3.0+7827+5e65edd7",
              "repositories": [
                {
                  "arch": "x86_64",
                  "name": "almalinux-8-powertools"
                }
              ],
              "version": "6.0.0"
            },
            {
              "arch": "i686",
              "epoch": 0,
              "name": "libvirt-daemon-driver-network-debuginfo",
              "release": "28.module+el8.3.0+7827+5e65edd7",
              "repositories": [
                {
                  "arch": "x86_64",
                  "name": "almalinux-8-powertools-debuginfo"
                }
              ],
              "version": "6.0.0"
            },
            {
              "arch": "i686",
              "epoch": 0,
              "name": "libvirt-daemon-driver-nodedev",
              "release": "28.module+el8.3.0+7827+5e65edd7",
              "repositories": [
                {
                  "arch": "x86_64",
                  "name": "almalinux-8-powertools"
                }
              ],
              "version": "6.0.0"
            },
            {
              "arch": "i686",
              "epoch": 0,
              "name": "libvirt-daemon-driver-nodedev-debuginfo",
              "release": "28.module+el8.3.0+7827+5e65edd7",
              "repositories": [
                {
                  "arch": "x86_64",
                  "name": "almalinux-8-powertools-debuginfo"
                }
              ],
              "version": "6.0.0"
            },
            {
              "arch": "i686",
              "epoch": 0,
              "name": "libvirt-daemon-driver-nwfilter",
              "release": "28.module+el8.3.0+7827+5e65edd7",
              "repositories": [
                {
                  "arch": "x86_64",
                  "name": "almalinux-8-powertools"
                }
              ],
              "version": "6.0.0"
            },
            {
              "arch": "i686",
              "epoch": 0,
              "name": "libvirt-daemon-driver-nwfilter-debuginfo",
              "release": "28.module+el8.3.0+7827+5e65edd7",
              "repositories": [
                {
                  "arch": "x86_64",
                  "name": "almalinux-8-powertools-debuginfo"
                }
              ],
              "version": "6.0.0"
            },
            {
              "arch": "i686",
              "epoch": 0,
              "name": "libvirt-daemon-driver-secret",
              "release": "28.module+el8.3.0+7827+5e65edd7",
              "repositories": [
                {
                  "arch": "x86_64",
                  "name": "almalinux-8-powertools"
                }
              ],
              "version": "6.0.0"
            },
            {
              "arch": "i686",
              "epoch": 0,
              "name": "libvirt-daemon-driver-secret-debuginfo",
              "release": "28.module+el8.3.0+7827+5e65edd7",
              "repositories": [
                {
                  "arch": "x86_64",
                  "name": "almalinux-8-powertools-debuginfo"
                }
              ],
              "version": "6.0.0"
            },
            {
              "arch": "i686",
              "epoch": 0,
              "name": "libvirt-daemon-driver-storage",
              "release": "28.module+el8.3.0+7827+5e65edd7",
              "repositories": [
                {
                  "arch": "x86_64",
                  "name": "almalinux-8-powertools"
                }
              ],
              "version": "6.0.0"
            },
            {
              "arch": "i686",
              "epoch": 0,
              "name": "libvirt-daemon-driver-storage-core",
              "release": "28.module+el8.3.0+7827+5e65edd7",
              "repositories": [
                {
                  "arch": "x86_64",
                  "name": "almalinux-8-powertools"
                }
              ],
              "version": "6.0.0"
            },
            {
              "arch": "i686",
              "epoch": 0,
              "name": "libvirt-daemon-driver-storage-core-debuginfo",
              "release": "28.module+el8.3.0+7827+5e65edd7",
              "repositories": [
                {
                  "arch": "x86_64",
                  "name": "almalinux-8-powertools-debuginfo"
                }
              ],
              "version": "6.0.0"
            },
            {
              "arch": "i686",
              "epoch": 0,
              "name": "libvirt-daemon-driver-storage-disk",
              "release": "28.module+el8.3.0+7827+5e65edd7",
              "repositories": [
                {
                  "arch": "x86_64",
                  "name": "almalinux-8-powertools"
                }
              ],
              "version": "6.0.0"
            },
            {
              "arch": "i686",
              "epoch": 0,
              "name": "libvirt-daemon-driver-storage-disk-debuginfo",
              "release": "28.module+el8.3.0+7827+5e65edd7",
              "repositories": [
                {
                  "arch": "x86_64",
                  "name": "almalinux-8-powertools-debuginfo"
                }
              ],
              "version": "6.0.0"
            },
            {
              "arch": "i686",
              "epoch": 0,
              "name": "libvirt-daemon-driver-storage-iscsi",
              "release": "28.module+el8.3.0+7827+5e65edd7",
              "repositories": [
                {
                  "arch": "x86_64",
                  "name": "almalinux-8-powertools"
                }
              ],
              "version": "6.0.0"
            },
            {
              "arch": "i686",
              "epoch": 0,
              "name": "libvirt-daemon-driver-storage-iscsi-debuginfo",
              "release": "28.module+el8.3.0+7827+5e65edd7",
              "repositories": [
                {
                  "arch": "x86_64",
                  "name": "almalinux-8-powertools-debuginfo"
                }
              ],
              "version": "6.0.0"
            },
            {
              "arch": "i686",
              "epoch": 0,
              "name": "libvirt-daemon-driver-storage-iscsi-direct",
              "release": "28.module+el8.3.0+7827+5e65edd7",
              "repositories": [
                {
                  "arch": "x86_64",
                  "name": "almalinux-8-powertools"
                }
              ],
              "version": "6.0.0"
            },
            {
              "arch": "i686",
              "epoch": 0,
              "name": "libvirt-daemon-driver-storage-iscsi-direct-debuginfo",
              "release": "28.module+el8.3.0+7827+5e65edd7",
              "repositories": [
                {
                  "arch": "x86_64",
                  "name": "almalinux-8-powertools-debuginfo"
                }
              ],
              "version": "6.0.0"
            },
            {
              "arch": "i686",
              "epoch": 0,
              "name": "libvirt-daemon-driver-storage-logical",
              "release": "28.module+el8.3.0+7827+5e65edd7",
              "repositories": [
                {
                  "arch": "x86_64",
                  "name": "almalinux-8-powertools"
                }
              ],
              "version": "6.0.0"
            },
            {
              "arch": "i686",
              "epoch": 0,
              "name": "libvirt-daemon-driver-storage-logical-debuginfo",
              "release": "28.module+el8.3.0+7827+5e65edd7",
              "repositories": [
                {
                  "arch": "x86_64",
                  "name": "almalinux-8-powertools-debuginfo"
                }
              ],
              "version": "6.0.0"
            },
            {
              "arch": "i686",
              "epoch": 0,
              "name": "libvirt-daemon-driver-storage-mpath",
              "release": "28.module+el8.3.0+7827+5e65edd7",
              "repositories": [
                {
                  "arch": "x86_64",
                  "name": "almalinux-8-powertools"
                }
              ],
              "version": "6.0.0"
            },
            {
              "arch": "i686",
              "epoch": 0,
              "name": "libvirt-daemon-driver-storage-mpath-debuginfo",
              "release": "28.module+el8.3.0+7827+5e65edd7",
              "repositories": [
                {
                  "arch": "x86_64",
                  "name": "almalinux-8-powertools-debuginfo"
                }
              ],
              "version": "6.0.0"
            },
            {
              "arch": "i686",
              "epoch": 0,
              "name": "libvirt-daemon-driver-storage-scsi",
              "release": "28.module+el8.3.0+7827+5e65edd7",
              "repositories": [
                {
                  "arch": "x86_64",
                  "name": "almalinux-8-powertools"
                }
              ],
              "version": "6.0.0"
            },
            {
              "arch": "i686",
              "epoch": 0,
              "name": "libvirt-daemon-driver-storage-scsi-debuginfo",
              "release": "28.module+el8.3.0+7827+5e65edd7",
              "repositories": [
                {
                  "arch": "x86_64",
                  "name": "almalinux-8-powertools-debuginfo"
                }
              ],
              "version": "6.0.0"
            },
            {
              "arch": "i686",
              "epoch": 0,
              "name": "libvirt-debuginfo",
              "release": "28.module+el8.3.0+7827+5e65edd7",
              "repositories": [
                {
                  "arch": "x86_64",
                  "name": "almalinux-8-powertools-debuginfo"
                }
              ],
              "version": "6.0.0"
            },
            {
              "arch": "i686",
              "epoch": 0,
              "name": "libvirt-debugsource",
              "release": "28.module+el8.3.0+7827+5e65edd7",
              "repositories": [
                {
                  "arch": "x86_64",
                  "name": "almalinux-8-powertools-debuginfo"
                }
              ],
              "version": "6.0.0"
            },
            {
              "arch": "i686",
              "epoch": 0,
              "name": "libvirt-devel",
              "release": "28.module+el8.3.0+7827+5e65edd7",
              "repositories": [
                {
                  "arch": "x86_64",
                  "name": "almalinux-8-powertools"
                }
              ],
              "version": "6.0.0"
            },
            {
              "arch": "i686",
              "epoch": 0,
              "name": "libvirt-docs",
              "release": "28.module+el8.3.0+7827+5e65edd7",
              "repositories": [
                {
                  "arch": "x86_64",
                  "name": "almalinux-8-powertools"
                }
              ],
              "version": "6.0.0"
            },
            {
              "arch": "i686",
              "epoch": 0,
              "name": "libvirt-libs",
              "release": "28.module+el8.3.0+7827+5e65edd7",
              "repositories": [
                {
                  "arch": "x86_64",
                  "name": "almalinux-8-powertools"
                }
              ],
              "version": "6.0.0"
            },
            {
              "arch": "i686",
              "epoch": 0,
              "name": "libvirt-libs-debuginfo",
              "release": "28.module+el8.3.0+7827+5e65edd7",
              "repositories": [
                {
                  "arch": "x86_64",
                  "name": "almalinux-8-powertools-debuginfo"
                }
              ],
              "version": "6.0.0"
            },
            {
              "arch": "i686",
              "epoch": 0,
              "name": "libvirt-nss",
              "release": "28.module+el8.3.0+7827+5e65edd7",
              "repositories": [
                {
                  "arch": "x86_64",
                  "name": "almalinux-8-powertools"
                }
              ],
              "version": "6.0.0"
            },
            {
              "arch": "i686",
              "epoch": 0,
              "name": "libvirt-nss-debuginfo",
              "release": "28.module+el8.3.0+7827+5e65edd7",
              "repositories": [
                {
                  "arch": "x86_64",
                  "name": "almalinux-8-powertools-debuginfo"
                }
              ],
              "version": "6.0.0"
            },
            {
              "arch": "i686",
              "epoch": 0,
              "name": "libvirt-wireshark",
              "release": "28.module+el8.3.0+7827+5e65edd7",
              "repositories": [
                {
                  "arch": "x86_64",
                  "name": "almalinux-8-powertools"
                }
              ],
              "version": "6.0.0"
            },
            {
              "arch": "i686",
              "epoch": 0,
              "name": "libvirt-wireshark-debuginfo",
              "release": "28.module+el8.3.0+7827+5e65edd7",
              "repositories": [
                {
                  "arch": "x86_64",
                  "name": "almalinux-8-powertools-debuginfo"
                }
              ],
              "version": "6.0.0"
            }
          ],
          "sourcerpm": {
            "name": "libvirt",
            "release": "28.module+el8.3.0+7827+5e65edd7",
            "version": "6.0.0"
          }
        },
        {
          "packages": [
            {
              "arch": "i686",
              "epoch": 0,
              "name": "libvirt-dbus",
              "release": "2.module+el8.3.0+6423+e4cb6418",
              "repositories": [
                {
                  "arch": "x86_64",
                  "name": "almalinux-8-powertools"
                }
              ],
              "version": "1.3.0"
            },
            {
              "arch": "i686",
              "epoch": 0,
              "name": "libvirt-dbus-debuginfo",
              "release": "2.module+el8.3.0+6423+e4cb6418",
              "repositories": [
                {
                  "arch": "x86_64",
                  "name": "almalinux-8-powertools-debuginfo"
                }
              ],
              "version": "1.3.0"
            },
            {
              "arch": "i686",
              "epoch": 0,
              "name": "libvirt-dbus-debugsource",
              "release": "2.module+el8.3.0+6423+e4cb6418",
              "repositories": [
                {
                  "arch": "x86_64",
                  "name": "almalinux-8-powertools-debuginfo"
                }
              ],
              "version": "1.3.0"
            }
          ],
          "sourcerpm": {
            "name": "libvirt-dbus",
            "release": "2.module+el8.3.0+6423+e4cb6418",
            "version": "1.3.0"
          }
        },
        {
          "packages": [
            {
              "arch": "i686",
              "epoch": 0,
              "name": "libvirt-python-debugsource",
              "release": "2.module+el8.3.0+6423+e4cb6418",
              "repositories": [
                {
                  "arch": "x86_64",
                  "name": "almalinux-8-powertools-debuginfo"
                }
              ],
              "version": "6.0.0"
            },
            {
              "arch": "i686",
              "epoch": 0,
              "name": "python3-libvirt",
              "release": "1.module+el8.3.0+6423+e4cb6418",
              "repositories": [
                {
                  "arch": "x86_64",
                  "name": "almalinux-8-powertools"
                }
              ],
              "version": "6.0.0"
            },
            {
              "arch": "i686",
              "epoch": 0,
              "name": "python3-libvirt-debuginfo",
              "release": "1.module+el8.3.0+6423+e4cb6418",
              "repositories": [
                {
                  "arch": "x86_64",
                  "name": "almalinux-8-powertools-debuginfo"
                }
              ],
              "version": "6.0.0"
            }
          ],
          "sourcerpm": {
            "name": "libvirt-python",
            "release": "1.module+el8.3.0+6423+e4cb6418",
            "version": "6.0.0"
          }
        },
        {
          "packages": [
            {
              "arch": "i686",
              "epoch": 0,
              "name": "netcf",
              "release": "12.module+el8.1.0+4066+0f1aadab",
              "repositories": [
                {
                  "arch": "x86_64",
                  "name": "almalinux-8-powertools"
                }
              ],
              "version": "0.2.8"
            },
            {
              "arch": "i686",
              "epoch": 0,
              "name": "netcf-debuginfo",
              "release": "12.module+el8.1.0+4066+0f1aadab",
              "repositories": [
                {
                  "arch": "x86_64",
                  "name": "almalinux-8-powertools-debuginfo"
                }
              ],
              "version": "0.2.8"
            },
            {
              "arch": "i686",
              "epoch": 0,
              "name": "netcf-debugsource",
              "release": "12.module+el8.1.0+4066+0f1aadab",
              "repositories": [
                {
                  "arch": "x86_64",
                  "name": "almalinux-8-powertools-debuginfo"
                }
              ],
              "version": "0.2.8"
            },
            {
              "arch": "i686",
              "epoch": 0,
              "name": "netcf-devel",
              "release": "12.module+el8.1.0+4066+0f1aadab",
              "repositories": [
                {
                  "arch": "x86_64",
                  "name": "almalinux-8-powertools"
                }
              ],
              "version": "0.2.8"
            },
            {
              "arch": "i686",
              "epoch": 0,
              "name": "netcf-libs",
              "release": "12.module+el8.1.0+4066+0f1aadab",
              "repositories": [
                {
                  "arch": "x86_64",
                  "name": "almalinux-8-powertools"
                }
              ],
              "version": "0.2.8"
            },
            {
              "arch": "i686",
              "epoch": 0,
              "name": "netcf-libs-debuginfo",
              "release": "12.module+el8.1.0+4066+0f1aadab",
              "repositories": [
                {
                  "arch": "x86_64",
                  "name": "almalinux-8-powertools-debuginfo"
                }
              ],
              "version": "0.2.8"
            }
          ],
          "sourcerpm": {
            "name": "netcf",
            "release": "12.module+el8.1.0+4066+0f1aadab",
            "version": "0.2.8"
          }
        },
        {
          "packages": [
            {
              "arch": "x86_64",
              "epoch": 1,
              "name": "ocaml-libguestfs",
              "release": "25.module+el8.3.0+7421+642fe24f",
              "repositories": [
                {
                  "arch": "x86_64",
                  "name": "almalinux-8-powertools"
                }
              ],
              "version": "1.40.2"
            },
            {
              "arch": "x86_64",
              "epoch": 1,
              "name": "ocaml-libguestfs-debuginfo",
              "release": "25.module+el8.3.0+7421+642fe24f",
              "repositories": [
                {
                  "arch": "x86_64",
                  "name": "almalinux-8-powertools-debuginfo"
                }
              ],
              "version": "1.40.2"
            },
            {
              "arch": "x86_64",
              "epoch": 1,
              "name": "ocaml-libguestfs-devel",
              "release": "25.module+el8.3.0+7421+642fe24f",
              "repositories": [
                {
                  "arch": "x86_64",
                  "name": "almalinux-8-powertools"
                }
              ],
              "version": "1.40.2"
            }
          ],
          "sourcerpm": {
            "epoch": 1,
            "name": "libguestfs",
            "release": "25.module+el8.3.0+7421+642fe24f",
            "version": "1.40.2"
          }
        },
        {
          "packages": [
            {
              "arch": "i686",
              "epoch": 0,
              "name": "perl-Sys-Virt",
              "release": "1.module+el8.3.0+6423+e4cb6418",
              "repositories": [
                {
                  "arch": "x86_64",
                  "name": "almalinux-8-powertools"
                }
              ],
              "version": "6.0.0"
            },
            {
              "arch": "i686",
              "epoch": 0,
              "name": "perl-Sys-Virt-debuginfo",
              "release": "1.module+el8.3.0+6423+e4cb6418",
              "repositories": [
                {
                  "arch": "x86_64",
                  "name": "almalinux-8-powertools-debuginfo"
                }
              ],
              "version": "6.0.0"
            },
            {
              "arch": "i686",
              "epoch": 0,
              "name": "perl-Sys-Virt-debugsource",
              "release": "1.module+el8.3.0+6423+e4cb6418",
              "repositories": [
                {
                  "arch": "x86_64",
                  "name": "almalinux-8-powertools-debuginfo"
                }
              ],
              "version": "6.0.0"
            }
          ],
          "sourcerpm": {
            "name": "perl-Sys-Virt",
            "release": "1.module+el8.3.0+6423+e4cb6418",
            "version": "6.0.0"
          }
        },
        {
          "packages": [
            {
              "arch": "x86_64",
              "epoch": 15,
              "name": "qemu-kvm-tests",
              "release": "34.module+el8.3.0+9903+ca3e42fb.4",
              "repositories": [
                {
                  "arch": "x86_64",
                  "name": "almalinux-8-powertools"
                }
              ],
              "version": "4.2.0"
            }
          ],
          "sourcerpm": {
            "epoch": 15,
            "name": "qemu-kvm",
            "release": "34.module+el8.3.0+9903+ca3e42fb.4",
            "version": "4.2.0"
          }
        },
        {
          "packages": [
            {
              "arch": "i686",
              "epoch": 1,
              "name": "sgabios",
              "release": "2.module+el8.3.0+7353+9de0a3cc",
              "repositories": [
                {
                  "arch": "x86_64",
                  "name": "almalinux-8-powertools"
                }
              ],
              "version": "0.20170427git"
            }
          ],
          "sourcerpm": {
            "name": "sgabios",
            "release": "2.module+el8.3.0+7353+9de0a3cc",
            "version": "0.20170427git"
          }
        },
        {
          "packages": [
            {
              "arch": "src",
              "epoch": 0,
              "name": "SLOF",
              "release": "3.git899d9883.module+el8.3.0+6423+e4cb6418",
              "repositories": [
                {
                  "arch": "src",
                  "name": "almalinux-8-powertools"
                }
              ],
              "version": "20191022"
            }
          ],
          "sourcerpm": {
            "epoch": 0,
            "name": "SLOF",
            "release": "3.git899d9883.module+el8.3.0+6423+e4cb6418",
            "version": "20191022"
          }
        }
      ],
      "context": "bd1311ed",
      "name": "virt-devel",
      "repository": {
        "arch": "x86_64",
        "name": "almalinux-8-powertools"
      },
      "stream": "rhel",
      "type": "module",
      "version": 8030020210210212009
    }
}

endpoint_response = modules_endpoint_response.copy()
for endpoint in modules_endpoint_response:
    for artifact in modules_endpoint_response[endpoint]["artifacts"]:
        src = artifact["sourcerpm"]
        if "epoch" in src:
            src_nevra = f"{src['name']}-{src['epoch']}:{src['version']}-{src['release']}"
        else:
            src_nevra = f"{src['name']}-0:{src['version']}-{src['release']}"
        endpoint = f"/api/v1/distros/AlmaLinux/8/project/{src_nevra}.src.rpm"
        if endpoint in endpoint_response:
            endpoint_response[endpoint]["packages"].extend(artifact["packages"])
        else:
            endpoint_response[endpoint] = {
                "distribution": {
                    "name": "AlmaLinux",
                    "version": "8"
                },
                "packages": artifact["packages"],
                "sourcerpm": src,
                "type": "package"
            }

@pytest.fixture
def beholder_responses():
    return endpoint_response

@pytest.fixture
def beholder_get(monkeypatch):
    async def func(*args, **kwargs):
        _, endpoint = args
        return endpoint_response[endpoint]

    monkeypatch.setattr(BeholderClient, "get", func)

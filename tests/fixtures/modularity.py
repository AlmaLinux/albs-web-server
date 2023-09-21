from asyncio import streams
import pytest


@pytest.fixture
def modules_yaml():
    return b"""
---
document: modulemd
version: 2
data:
  name: go-toolset
  stream: "rhel8"
  version: 8070020230125092346
  context: b754926a
  arch: x86_64
  summary: Go
  description: >-
    Go Tools and libraries
  license:
    module:
    - MIT
  dependencies:
  - buildrequires:
      go-toolset: [rhel8]
      platform: [el8]
    requires:
      platform: [el8]
  profiles:
    common:
      rpms:
      - go-toolset
  api:
    rpms:
    - golang
  buildopts:
    rpms:
      whitelist:
      - delve
      - go-toolset
      - go-toolset-1.10
      - go-toolset-1.10-golang
      - go-toolset-golang
      - golang
  components:
    rpms:
      delve:
        rationale: A debugger for the Go programming language
        ref: 18f55f0e6d4d9579ac949e3a96c1c2f6e877cba8
        buildorder: 2
        arches: [aarch64, i686, ppc64le, s390x, x86_64]
      go-toolset:
        rationale: Meta package for go-toolset providing scl enable scripts.
        ref: feda7855f214faf3cbb4324c74a47e4a00d117a8
        arches: [aarch64, i686, ppc64le, s390x, x86_64]
      golang:
        rationale: Package providing the Go compiler toolchain.
        ref: 61d02fbf0e5553e82c220cfb2f403338f43496b6
        buildorder: 1
        arches: [aarch64, i686, ppc64le, s390x, x86_64]
  artifacts:
    rpms:
    - delve-0:1.8.3-1.module_el8.7.0+3280+24dc9c5d.src
    - delve-0:1.8.3-1.module_el8.7.0+3280+24dc9c5d.x86_64
    - delve-debuginfo-0:1.8.3-1.module_el8.7.0+3280+24dc9c5d.x86_64
    - delve-debugsource-0:1.8.3-1.module_el8.7.0+3280+24dc9c5d.x86_64
    - go-toolset-0:1.18.9-1.module_el8.7.0+3397+4350156d.src
    - go-toolset-0:1.18.9-1.module_el8.7.0+3397+4350156d.x86_64
    - golang-0:1.18.9-1.module_el8.7.0+3397+4350156d.src
    - golang-0:1.18.9-1.module_el8.7.0+3397+4350156d.x86_64
    - golang-bin-0:1.18.9-1.module_el8.7.0+3397+4350156d.x86_64
    - golang-docs-0:1.18.9-1.module_el8.7.0+3397+4350156d.noarch
    - golang-misc-0:1.18.9-1.module_el8.7.0+3397+4350156d.noarch
    - golang-race-0:1.18.9-1.module_el8.7.0+3397+4350156d.x86_64
    - golang-src-0:1.18.9-1.module_el8.7.0+3397+4350156d.noarch
    - golang-tests-0:1.18.9-1.module_el8.7.0+3397+4350156d.noarch
...
---
document: modulemd
version: 2
data:
  name: go-toolset-devel
  stream: "rhel8"
  version: 8070020230125092346
  context: b754926a
  arch: x86_64
  summary: Go
  description: >-
    Go Tools and libraries
  license:
    module:
    - MIT
  dependencies:
  - buildrequires:
      go-toolset: [rhel8]
      platform: [el8]
    requires:
      go-toolset: [rhel8]
      platform: [el8]
  profiles:
    common:
      rpms:
      - go-toolset
  api:
    rpms:
    - golang
  buildopts:
    rpms:
      whitelist:
      - delve
      - go-toolset
      - go-toolset-1.10
      - go-toolset-1.10-golang
      - go-toolset-golang
      - golang
  components:
    rpms:
      delve:
        rationale: A debugger for the Go programming language
        ref: 18f55f0e6d4d9579ac949e3a96c1c2f6e877cba8
        buildorder: 2
        arches: [aarch64, i686, ppc64le, s390x, x86_64]
      go-toolset:
        rationale: Meta package for go-toolset providing scl enable scripts.
        ref: feda7855f214faf3cbb4324c74a47e4a00d117a8
        arches: [aarch64, i686, ppc64le, s390x, x86_64]
      golang:
        rationale: Package providing the Go compiler toolchain.
        ref: 61d02fbf0e5553e82c220cfb2f403338f43496b6
        buildorder: 1
        arches: [aarch64, i686, ppc64le, s390x, x86_64]
...
    """


@pytest.fixture
def modules_yaml_with_filter():
    return b"""
---
document: modulemd
version: 2
data:
  name: 389-ds
  stream: "1.4"
  version: 8060020221025134811
  context: 17499975
  arch: x86_64
  summary: 389 Directory Server (base)
  description: >-
    389 Directory Server is an LDAPv3 compliant server.  The base package includes
    the LDAP server and command line utilities for server administration.
  license:
    module:
    - MIT
  dependencies:
  - buildrequires:
      llvm-toolset: [rhel8]
      nodejs: [10]
      platform: [el8]
      rust-toolset: [rhel8]
    requires:
      platform: [el8]
  filter:
    rpms:
    - cockpit-389-ds
  components:
    rpms:
      389-ds-base:
        rationale: Package in api
        ref: ceb31709f5d2533dd667c9c958acb48edae497d3
        arches: [aarch64, i686, ppc64le, s390x, x86_64]
  artifacts:
    rpms:
    - 389-ds-base-0:1.4.3.28-8.module_el8.6.0+3338+ebccfef1.src
    - 389-ds-base-0:1.4.3.28-8.module_el8.6.0+3338+ebccfef1.x86_64
    - 389-ds-base-debuginfo-0:1.4.3.28-8.module_el8.6.0+3338+ebccfef1.x86_64
    - 389-ds-base-debugsource-0:1.4.3.28-8.module_el8.6.0+3338+ebccfef1.x86_64
    - 389-ds-base-devel-0:1.4.3.28-8.module_el8.6.0+3338+ebccfef1.x86_64
    - 389-ds-base-legacy-tools-0:1.4.3.28-8.module_el8.6.0+3338+ebccfef1.x86_64
    - 389-ds-base-legacy-tools-debuginfo-0:1.4.3.28-8.module_el8.6.0+3338+ebccfef1.x86_64
    - 389-ds-base-libs-0:1.4.3.28-8.module_el8.6.0+3338+ebccfef1.x86_64
    - 389-ds-base-libs-debuginfo-0:1.4.3.28-8.module_el8.6.0+3338+ebccfef1.x86_64
    - 389-ds-base-snmp-0:1.4.3.28-8.module_el8.6.0+3338+ebccfef1.x86_64
    - 389-ds-base-snmp-debuginfo-0:1.4.3.28-8.module_el8.6.0+3338+ebccfef1.x86_64
    - python3-lib389-0:1.4.3.28-8.module_el8.6.0+3338+ebccfef1.noarch
...
---
document: modulemd
version: 2
data:
  name: 389-ds-devel
  stream: "1.4"
  version: 8060020221025134811
  context: 17499975
  arch: x86_64
  summary: 389 Directory Server (base)
  description: >-
    389 Directory Server is an LDAPv3 compliant server.  The base package includes
    the LDAP server and command line utilities for server administration.
  license:
    module:
    - MIT
  dependencies:
  - buildrequires:
      llvm-toolset: [rhel8]
      nodejs: [10]
      platform: [el8]
      rust-toolset: [rhel8]
    requires:
      platform: [el8]
  filter:
    rpms:
    - cockpit-389-ds
  components:
    rpms:
      389-ds-base:
        rationale: Package in api
        ref: ceb31709f5d2533dd667c9c958acb48edae497d3
        arches: [aarch64, i686, ppc64le, s390x, x86_64]
  artifacts:
    rpms:
    - cockpit-389-ds-0:1.4.3.28-8.module_el8.6.0+3338+ebccfef1.noarch
...
    """


@pytest.fixture
def multilib_virt_with_artifacts():
    return """
---
document: modulemd
version: 2
data:
  name: virt
  stream: rhel
  version: 8030020210210212009
  context: 229f0a1c
  arch: x86_64
  summary: Virtualization module
  description: >-
    A virtualization module
  license:
    module:
    - MIT
    content:
    - ASL 2.0
    - BSD
    - GPLv2 and GPLv2+ and CC-BY
    - GPLv2+
    - GPLv2+ or Artistic
    - LGPLv2
    - LGPLv2+
    - LGPLv2+ and BSD
    - LGPLv3
  dependencies:
  - buildrequires:
      platform: [el8.3.0.z]
    requires:
      platform: [el8]
  profiles:
    common:
      rpms:
      - libguestfs
      - libvirt-client
      - libvirt-daemon-config-network
      - libvirt-daemon-kvm
  filter:
    rpms:
    - ocaml-hivex
    - ocaml-hivex-debuginfo
    - ocaml-hivex-devel
    - ocaml-libguestfs
    - ocaml-libguestfs-debuginfo
    - ocaml-libguestfs-devel
    - ocaml-libnbd
    - ocaml-libnbd-debuginfo
    - ocaml-libnbd-devel
    - qemu-kvm-tests
    - qemu-kvm-tests-debuginfo
  components:
    rpms:
      SLOF:
        rationale: qemu-kvm dep
        ref: stream-rhel-rhel-8.3.0
        buildorder: 1
        arches: [ppc64le]
      hivex:
        rationale: libguestfs dep
        ref: stream-rhel-rhel-8.3.0
        buildorder: 1
        arches: [aarch64, i686, ppc64le, s390x, x86_64]
      libguestfs:
        rationale: Primary module content
        ref: stream-rhel-rhel-8.3.0
        buildorder: 4
        arches: [aarch64, i686, ppc64le, s390x, x86_64]
      libguestfs-winsupport:
        rationale: Primary module content
        ref: stream-rhel-rhel-8.3.0
        buildorder: 5
        arches: [aarch64, i686, ppc64le, s390x, x86_64]
      libiscsi:
        rationale: qemu-kvm dep
        ref: stream-rhel-rhel-8.3.0
        buildorder: 1
        arches: [aarch64, i686, ppc64le, s390x, x86_64]
      libnbd:
        rationale: Primary module content
        ref: stream-rhel-rhel-8.3.0
        buildorder: 1
        arches: [aarch64, i686, ppc64le, s390x, x86_64]
      libvirt:
        rationale: Primary module content
        ref: stream-rhel-rhel-8.3.0
        buildorder: 3
        arches: [aarch64, i686, ppc64le, s390x, x86_64]
      libvirt-dbus:
        rationale: libvirt-dbus is part of the virtualization module
        ref: stream-rhel-rhel-8.3.0
        buildorder: 4
        arches: [aarch64, i686, ppc64le, s390x, x86_64]
      libvirt-python:
        rationale: Primary module content
        ref: stream-rhel-rhel-8.3.0
        buildorder: 4
        arches: [aarch64, i686, ppc64le, s390x, x86_64]
      nbdkit:
        rationale: Primary module content
        ref: stream-rhel-rhel-8.3.0
        buildorder: 5
        arches: [aarch64, i686, ppc64le, s390x, x86_64]
      netcf:
        rationale: libvirt dep
        ref: stream-rhel-rhel-8.3.0
        buildorder: 1
        arches: [aarch64, i686, ppc64le, s390x, x86_64]
      perl-Sys-Virt:
        rationale: Primary module content
        ref: stream-rhel-rhel-8.3.0
        buildorder: 4
        arches: [aarch64, i686, ppc64le, s390x, x86_64]
      qemu-kvm:
        rationale: Primary module content
        ref: stream-rhel-rhel-8.3.0
        buildorder: 2
        arches: [aarch64, i686, ppc64le, s390x, x86_64]
      seabios:
        rationale: qemu-kvm dep
        ref: stream-rhel-rhel-8.3.0
        buildorder: 1
        arches: [ppc64le, x86_64]
      sgabios:
        rationale: qemu-kvm dep
        ref: stream-rhel-rhel-8.3.0
        buildorder: 1
        arches: [ppc64le, x86_64]
      supermin:
        rationale: libguestfs dep
        ref: stream-rhel-rhel-8.3.0
        buildorder: 2
        arches: [aarch64, i686, ppc64le, s390x, x86_64]
  artifacts:
    rpms:
    - hivex-0:1.3.18-23.module_el8.6.0+2880+7d9e3703.src
    - hivex-0:1.3.18-23.module_el8.6.0+2880+7d9e3703.x86_64
    - hivex-debuginfo-0:1.3.18-23.module_el8.6.0+2880+7d9e3703.x86_64
    - hivex-debugsource-0:1.3.18-23.module_el8.6.0+2880+7d9e3703.x86_64
    - hivex-devel-0:1.3.18-23.module_el8.6.0+2880+7d9e3703.x86_64
    - qemu-kvm-0:6.2.0-32.module_el8.8.0+3553+bd08596b.src
    - qemu-kvm-0:6.2.0-32.module_el8.8.0+3553+bd08596b.x86_64
    - qemu-kvm-debuginfo-0:6.2.0-32.module_el8.8.0+3553+bd08596b.x86_64
    - qemu-kvm-debugsource-0:6.2.0-32.module_el8.8.0+3553+bd08596b.x86_64
...
---
document: modulemd
version: 2
data:
  name: virt-devel
  stream: rhel
  version: 8030020210210212009
  context: 229f0a1c
  arch: x86_64
  summary: Virtualization module
  description: >-
    A virtualization module
  license:
    module:
    - MIT
    content:
    - ASL 2.0
    - GPLv2 and GPLv2+ and CC-BY
    - GPLv2+
    - GPLv2+ or Artistic
    - LGPLv2
    - LGPLv2+
    - LGPLv2+ and BSD
  dependencies:
  - buildrequires:
      platform: [el8.3.0.z]
    requires:
      platform: [el8]
      virt-devel: [rhel]
  filter:
    rpms:
    - ocaml-hivex
    - ocaml-hivex-debuginfo
    - ocaml-hivex-devel
    - ocaml-libguestfs
    - ocaml-libguestfs-debuginfo
    - ocaml-libguestfs-devel
    - ocaml-libnbd
    - ocaml-libnbd-debuginfo
    - ocaml-libnbd-devel
    - qemu-kvm-tests
    - qemu-kvm-tests-debuginfo
  components:
    rpms:
      SLOF:
        rationale: qemu-kvm dep
        ref: stream-rhel-rhel-8.3.0
        buildorder: 1
        arches: [ppc64le]
      hivex:
        rationale: libguestfs dep
        ref: stream-rhel-rhel-8.3.0
        buildorder: 1
        arches: [aarch64, i686, ppc64le, s390x, x86_64]
      libguestfs:
        rationale: Primary module content
        ref: stream-rhel-rhel-8.3.0
        buildorder: 4
        arches: [aarch64, i686, ppc64le, s390x, x86_64]
      libguestfs-winsupport:
        rationale: Primary module content
        ref: stream-rhel-rhel-8.3.0
        buildorder: 5
        arches: [aarch64, i686, ppc64le, s390x, x86_64]
      libiscsi:
        rationale: qemu-kvm dep
        ref: stream-rhel-rhel-8.3.0
        buildorder: 1
        arches: [aarch64, i686, ppc64le, s390x, x86_64]
      libnbd:
        rationale: Primary module content
        ref: stream-rhel-rhel-8.3.0
        buildorder: 1
        arches: [aarch64, i686, ppc64le, s390x, x86_64]
      libvirt:
        rationale: Primary module content
        ref: stream-rhel-rhel-8.3.0
        buildorder: 3
        arches: [aarch64, i686, ppc64le, s390x, x86_64]
      libvirt-dbus:
        rationale: libvirt-dbus is part of the virtualization module
        ref: stream-rhel-rhel-8.3.0
        buildorder: 4
        arches: [aarch64, i686, ppc64le, s390x, x86_64]
      libvirt-python:
        rationale: Primary module content
        ref: stream-rhel-rhel-8.3.0
        buildorder: 4
        arches: [aarch64, i686, ppc64le, s390x, x86_64]
      nbdkit:
        rationale: Primary module content
        ref: stream-rhel-rhel-8.3.0
        buildorder: 5
        arches: [aarch64, i686, ppc64le, s390x, x86_64]
      netcf:
        rationale: libvirt dep
        ref: stream-rhel-rhel-8.3.0
        buildorder: 1
        arches: [aarch64, i686, ppc64le, s390x, x86_64]
      perl-Sys-Virt:
        rationale: Primary module content
        ref: stream-rhel-rhel-8.3.0
        buildorder: 4
        arches: [aarch64, i686, ppc64le, s390x, x86_64]
      qemu-kvm:
        rationale: Primary module content
        ref: stream-rhel-rhel-8.3.0
        buildorder: 2
        arches: [aarch64, i686, ppc64le, s390x, x86_64]
      seabios:
        rationale: qemu-kvm dep
        ref: stream-rhel-rhel-8.3.0
        buildorder: 1
        arches: [ppc64le, x86_64]
      sgabios:
        rationale: qemu-kvm dep
        ref: stream-rhel-rhel-8.3.0
        buildorder: 1
        arches: [ppc64le, x86_64]
      supermin:
        rationale: libguestfs dep
        ref: stream-rhel-rhel-8.3.0
        buildorder: 2
        arches: [aarch64, i686, ppc64le, s390x, x86_64]
  artifacts:
    rpms:
    - SLOF-0:20210217-1.module_el8.6.0+2880+7d9e3703.src
    - hivex-0:1.3.18-23.module_el8.6.0+2880+7d9e3703.i686
    - hivex-debuginfo-0:1.3.18-23.module_el8.6.0+2880+7d9e3703.i686
    - hivex-debugsource-0:1.3.18-23.module_el8.6.0+2880+7d9e3703.i686
    - hivex-devel-0:1.3.18-23.module_el8.6.0+2880+7d9e3703.i686
    - ocaml-hivex-0:1.3.18-23.module_el8.6.0+2880+7d9e3703.i686
    - ocaml-hivex-0:1.3.18-23.module_el8.6.0+2880+7d9e3703.x86_64
    - ocaml-hivex-debuginfo-0:1.3.18-23.module_el8.6.0+2880+7d9e3703.i686
    - ocaml-hivex-debuginfo-0:1.3.18-23.module_el8.6.0+2880+7d9e3703.x86_64
    - ocaml-hivex-devel-0:1.3.18-23.module_el8.6.0+2880+7d9e3703.i686
    - ocaml-hivex-devel-0:1.3.18-23.module_el8.6.0+2880+7d9e3703.x86_64
...
    """


@pytest.fixture
def virt_artifacts():
  return {
    "virt:ppc64le":
      [
        "SLOF-0:20210217-1.module_el8.6.0+2880+7d9e3703.noarch",
        "SLOF-0:20210217-1.module_el8.6.0+2880+7d9e3703.src",
        "hivex-0:1.3.18-23.module_el8.6.0+2880+7d9e3703.ppc64le",
        "hivex-0:1.3.18-23.module_el8.6.0+2880+7d9e3703.src",
        "hivex-debuginfo-0:1.3.18-23.module_el8.6.0+2880+7d9e3703.ppc64le",
        "hivex-debugsource-0:1.3.18-23.module_el8.6.0+2880+7d9e3703.ppc64le",
        "hivex-devel-0:1.3.18-23.module_el8.6.0+2880+7d9e3703.ppc64le",
        "qemu-kvm-0:6.2.0-32.module_el8.8.0+3553+bd08596b.ppc64le",
        "qemu-kvm-0:6.2.0-32.module_el8.8.0+3553+bd08596b.src",
        "qemu-kvm-debuginfo-0:6.2.0-32.module_el8.8.0+3553+bd08596b.ppc64le",
        "qemu-kvm-debugsource-0:6.2.0-32.module_el8.8.0+3553+bd08596b.ppc64le",
      ],
    "virt-devel:ppc64le":
      [
      "ocaml-hivex-0:1.3.18-23.module_el8.6.0+2880+7d9e3703.ppc64le",
      "ocaml-hivex-debuginfo-0:1.3.18-23.module_el8.6.0+2880+7d9e3703.ppc64le",
      "ocaml-hivex-devel-0:1.3.18-23.module_el8.6.0+2880+7d9e3703.ppc64le",
    ],
    "virt:i686":
      [ 
        "hivex-0:1.3.18-23.module_el8.6.0+2880+7d9e3703.i686",
        "hivex-0:1.3.18-23.module_el8.6.0+2880+7d9e3703.src",
        "hivex-debuginfo-0:1.3.18-23.module_el8.6.0+2880+7d9e3703.i686",
        "hivex-debugsource-0:1.3.18-23.module_el8.6.0+2880+7d9e3703.i686",
        "hivex-devel-0:1.3.18-23.module_el8.6.0+2880+7d9e3703.i686",
      ],
    "virt-devel:i686":
      [
      "SLOF-0:20210217-1.module_el8.6.0+2880+7d9e3703.src",
      "ocaml-hivex-0:1.3.18-23.module_el8.6.0+2880+7d9e3703.i686",
      "ocaml-hivex-debuginfo-0:1.3.18-23.module_el8.6.0+2880+7d9e3703.i686",
      "ocaml-hivex-devel-0:1.3.18-23.module_el8.6.0+2880+7d9e3703.i686",
      "qemu-kvm-0:6.2.0-32.module_el8.8.0+3553+bd08596b.src",
    ],
  }


@pytest.fixture
def virt_template():
    return """
---
document: modulemd
version: 2
data:
  stream: rhel
  summary: Virtualization module
  description: A virtualization module
  license:
    module:
      - MIT
  dependencies:
    - buildrequires:
        platform: [el8]
      requires:
        platform: [el8]
  profiles:
    common:
      rpms:
        - libguestfs
        - libvirt-client
        - libvirt-daemon-config-network
        - libvirt-daemon-kvm
  filter:
    rpms:
      - ocaml-hivex
      - ocaml-hivex-debuginfo
      - ocaml-hivex-devel
      - ocaml-libguestfs
      - ocaml-libguestfs-debuginfo
      - ocaml-libguestfs-devel
      - ocaml-libnbd
      - ocaml-libnbd-debuginfo
      - ocaml-libnbd-devel
      - qemu-kvm-tests
      - qemu-kvm-tests-debuginfo
  components:
    rpms:
      SLOF:
        rationale: qemu-kvm dep
        ref: stream-rhel-rhel-8.8.0
        buildorder: 1
        arches: [ppc64le]
      hivex:
        rationale: libguestfs dep
        ref: stream-rhel-rhel-8.8.0
        buildorder: 1
      libguestfs:
        rationale: Primary module content
        ref: stream-rhel-rhel-8.8.0
        buildorder: 4
      libguestfs-winsupport:
        rationale: Primary module content
        ref: stream-rhel-rhel-8.8.0
        buildorder: 5
      libiscsi:
        rationale: qemu-kvm dep
        ref: stream-rhel-rhel-8.8.0
        buildorder: 1
      libvirt:
        rationale: Primary module content
        ref: stream-rhel-rhel-8.8.0
        buildorder: 3
      libvirt-dbus:
        rationale: libvirt-dbus is part of the virtualization module
        ref: stream-rhel-rhel-8.8.0
        buildorder: 4
      libvirt-python:
        rationale: Primary module content
        ref: stream-rhel-rhel-8.8.0
        buildorder: 4
      libnbd:
        rationale: Primary module content
        ref: stream-rhel-rhel-8.8.0
        buildorder: 1
      nbdkit:
        rationale: Primary module content
        ref: stream-rhel-rhel-8.8.0
        buildorder: 5
      netcf:
        rationale: libvirt dep
        ref: stream-rhel-rhel-8.8.0
        buildorder: 1
      perl-Sys-Virt:
        rationale: Primary module content
        ref: stream-rhel-rhel-8.8.0
        buildorder: 4
      qemu-kvm:
        rationale: Primary module content
        ref: stream-rhel-rhel-8.8.0
        buildorder: 2
      seabios:
        rationale: qemu-kvm dep
        ref: stream-rhel-rhel-8.8.0
        buildorder: 1
        arches: [ppc64le, x86_64]
      sgabios:
        rationale: qemu-kvm dep
        ref: stream-rhel-rhel-8.8.0
        buildorder: 1
        arches: [ppc64le, x86_64]
      supermin:
        rationale: libguestfs dep
        ref: stream-rhel-rhel-8.8.0
        buildorder: 2
      libtpms:
        rationale: Primary module content
        ref: stream-rhel-rhel-8.8.0
        buildorder: 1
      swtpm:
        rationale: Primary module content
        ref: stream-rhel-rhel-8.8.0
        buildorder: 2
      virt-v2v:
        rationale: Primary module content
        ref: stream-rhel-rhel-8.8.0
        buildorder: 6
    """

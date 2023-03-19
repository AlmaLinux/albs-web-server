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
def modules_yaml_virt():
    return b"""
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
    - hivex-0:1.3.18-20.module+el8.3.0+6423+e4cb6418.src
    - hivex-0:1.3.18-20.module+el8.3.0+6423+e4cb6418.x86_64
    - hivex-debuginfo-0:1.3.18-20.module+el8.3.0+6423+e4cb6418.x86_64
    - hivex-debugsource-0:1.3.18-20.module+el8.3.0+6423+e4cb6418.x86_64
    - hivex-devel-0:1.3.18-20.module+el8.3.0+6423+e4cb6418.x86_64
    - libguestfs-1:1.40.2-25.module+el8.3.0+7421+642fe24f.src
    - libguestfs-1:1.40.2-25.module+el8.3.0+7421+642fe24f.x86_64
    - libguestfs-bash-completion-1:1.40.2-25.module+el8.3.0+7421+642fe24f.noarch
    - libguestfs-benchmarking-1:1.40.2-25.module+el8.3.0+7421+642fe24f.x86_64
    - libguestfs-benchmarking-debuginfo-1:1.40.2-25.module+el8.3.0+7421+642fe24f.x86_64
    - libguestfs-debuginfo-1:1.40.2-25.module+el8.3.0+7421+642fe24f.x86_64
    - libguestfs-debugsource-1:1.40.2-25.module+el8.3.0+7421+642fe24f.x86_64
    - libguestfs-devel-1:1.40.2-25.module+el8.3.0+7421+642fe24f.x86_64
    - libguestfs-gfs2-1:1.40.2-25.module+el8.3.0+7421+642fe24f.x86_64
    - libguestfs-gobject-1:1.40.2-25.module+el8.3.0+7421+642fe24f.x86_64
    - libguestfs-gobject-debuginfo-1:1.40.2-25.module+el8.3.0+7421+642fe24f.x86_64
    - libguestfs-gobject-devel-1:1.40.2-25.module+el8.3.0+7421+642fe24f.x86_64
    - libguestfs-inspect-icons-1:1.40.2-25.module+el8.3.0+7421+642fe24f.noarch
    - libguestfs-java-1:1.40.2-25.module+el8.3.0+7421+642fe24f.x86_64
    - libguestfs-java-debuginfo-1:1.40.2-25.module+el8.3.0+7421+642fe24f.x86_64
    - libguestfs-java-devel-1:1.40.2-25.module+el8.3.0+7421+642fe24f.x86_64
    - libguestfs-javadoc-1:1.40.2-25.module+el8.3.0+7421+642fe24f.noarch
    - libguestfs-man-pages-ja-1:1.40.2-25.module+el8.3.0+7421+642fe24f.noarch
    - libguestfs-man-pages-uk-1:1.40.2-25.module+el8.3.0+7421+642fe24f.noarch
    - libguestfs-rescue-1:1.40.2-25.module+el8.3.0+7421+642fe24f.x86_64
    - libguestfs-rsync-1:1.40.2-25.module+el8.3.0+7421+642fe24f.x86_64
    - libguestfs-tools-1:1.40.2-25.module+el8.3.0+7421+642fe24f.noarch
    - libguestfs-tools-c-1:1.40.2-25.module+el8.3.0+7421+642fe24f.x86_64
    - libguestfs-tools-c-debuginfo-1:1.40.2-25.module+el8.3.0+7421+642fe24f.x86_64
    - libguestfs-winsupport-0:8.2-1.module+el8.3.0+6423+e4cb6418.src
    - libguestfs-winsupport-0:8.2-1.module+el8.3.0+6423+e4cb6418.x86_64
    - libguestfs-xfs-1:1.40.2-25.module+el8.3.0+7421+642fe24f.x86_64
    - libiscsi-0:1.18.0-8.module+el8.1.0+4066+0f1aadab.src
    - libiscsi-0:1.18.0-8.module+el8.1.0+4066+0f1aadab.x86_64
    - libiscsi-debuginfo-0:1.18.0-8.module+el8.1.0+4066+0f1aadab.x86_64
    - libiscsi-debugsource-0:1.18.0-8.module+el8.1.0+4066+0f1aadab.x86_64
    - libiscsi-devel-0:1.18.0-8.module+el8.1.0+4066+0f1aadab.x86_64
    - libiscsi-utils-0:1.18.0-8.module+el8.1.0+4066+0f1aadab.x86_64
    - libiscsi-utils-debuginfo-0:1.18.0-8.module+el8.1.0+4066+0f1aadab.x86_64
    - libnbd-0:1.2.2-1.module+el8.3.0+7353+9de0a3cc.src
    - libnbd-0:1.2.2-1.module+el8.3.0+7353+9de0a3cc.x86_64
    - libnbd-debuginfo-0:1.2.2-1.module+el8.3.0+7353+9de0a3cc.x86_64
    - libnbd-debugsource-0:1.2.2-1.module+el8.3.0+7353+9de0a3cc.x86_64
    - libnbd-devel-0:1.2.2-1.module+el8.3.0+7353+9de0a3cc.x86_64
    - libvirt-0:6.0.0-28.module+el8.3.0+7827+5e65edd7.src
    - libvirt-0:6.0.0-28.module+el8.3.0+7827+5e65edd7.x86_64
    - libvirt-admin-0:6.0.0-28.module+el8.3.0+7827+5e65edd7.x86_64
    - libvirt-admin-debuginfo-0:6.0.0-28.module+el8.3.0+7827+5e65edd7.x86_64
    - libvirt-bash-completion-0:6.0.0-28.module+el8.3.0+7827+5e65edd7.x86_64
    - libvirt-client-0:6.0.0-28.module+el8.3.0+7827+5e65edd7.x86_64
    - libvirt-client-debuginfo-0:6.0.0-28.module+el8.3.0+7827+5e65edd7.x86_64
    - libvirt-daemon-0:6.0.0-28.module+el8.3.0+7827+5e65edd7.x86_64
    - libvirt-daemon-config-network-0:6.0.0-28.module+el8.3.0+7827+5e65edd7.x86_64
    - libvirt-daemon-config-nwfilter-0:6.0.0-28.module+el8.3.0+7827+5e65edd7.x86_64
    - libvirt-daemon-debuginfo-0:6.0.0-28.module+el8.3.0+7827+5e65edd7.x86_64
    - libvirt-daemon-driver-interface-0:6.0.0-28.module+el8.3.0+7827+5e65edd7.x86_64
    - libvirt-daemon-driver-interface-debuginfo-0:6.0.0-28.module+el8.3.0+7827+5e65edd7.x86_64
    - libvirt-daemon-driver-network-0:6.0.0-28.module+el8.3.0+7827+5e65edd7.x86_64
    - libvirt-daemon-driver-network-debuginfo-0:6.0.0-28.module+el8.3.0+7827+5e65edd7.x86_64
    - libvirt-daemon-driver-nodedev-0:6.0.0-28.module+el8.3.0+7827+5e65edd7.x86_64
    - libvirt-daemon-driver-nodedev-debuginfo-0:6.0.0-28.module+el8.3.0+7827+5e65edd7.x86_64
    - libvirt-daemon-driver-nwfilter-0:6.0.0-28.module+el8.3.0+7827+5e65edd7.x86_64
    - libvirt-daemon-driver-nwfilter-debuginfo-0:6.0.0-28.module+el8.3.0+7827+5e65edd7.x86_64
    - libvirt-daemon-driver-qemu-0:6.0.0-28.module+el8.3.0+7827+5e65edd7.x86_64
    - libvirt-daemon-driver-qemu-debuginfo-0:6.0.0-28.module+el8.3.0+7827+5e65edd7.x86_64
    - libvirt-daemon-driver-secret-0:6.0.0-28.module+el8.3.0+7827+5e65edd7.x86_64
    - libvirt-daemon-driver-secret-debuginfo-0:6.0.0-28.module+el8.3.0+7827+5e65edd7.x86_64
    - libvirt-daemon-driver-storage-0:6.0.0-28.module+el8.3.0+7827+5e65edd7.x86_64
    - libvirt-daemon-driver-storage-core-0:6.0.0-28.module+el8.3.0+7827+5e65edd7.x86_64
    - libvirt-daemon-driver-storage-core-debuginfo-0:6.0.0-28.module+el8.3.0+7827+5e65edd7.x86_64
    - libvirt-daemon-driver-storage-disk-0:6.0.0-28.module+el8.3.0+7827+5e65edd7.x86_64
    - libvirt-daemon-driver-storage-disk-debuginfo-0:6.0.0-28.module+el8.3.0+7827+5e65edd7.x86_64
    - libvirt-daemon-driver-storage-gluster-0:6.0.0-28.module+el8.3.0+7827+5e65edd7.x86_64
    - libvirt-daemon-driver-storage-gluster-debuginfo-0:6.0.0-28.module+el8.3.0+7827+5e65edd7.x86_64
    - libvirt-daemon-driver-storage-iscsi-0:6.0.0-28.module+el8.3.0+7827+5e65edd7.x86_64
    - libvirt-daemon-driver-storage-iscsi-debuginfo-0:6.0.0-28.module+el8.3.0+7827+5e65edd7.x86_64
    - libvirt-daemon-driver-storage-iscsi-direct-0:6.0.0-28.module+el8.3.0+7827+5e65edd7.x86_64
    - libvirt-daemon-driver-storage-iscsi-direct-debuginfo-0:6.0.0-28.module+el8.3.0+7827+5e65edd7.x86_64
    - libvirt-daemon-driver-storage-logical-0:6.0.0-28.module+el8.3.0+7827+5e65edd7.x86_64
    - libvirt-daemon-driver-storage-logical-debuginfo-0:6.0.0-28.module+el8.3.0+7827+5e65edd7.x86_64
    - libvirt-daemon-driver-storage-mpath-0:6.0.0-28.module+el8.3.0+7827+5e65edd7.x86_64
    - libvirt-daemon-driver-storage-mpath-debuginfo-0:6.0.0-28.module+el8.3.0+7827+5e65edd7.x86_64
    - libvirt-daemon-driver-storage-rbd-0:6.0.0-28.module+el8.3.0+7827+5e65edd7.x86_64
    - libvirt-daemon-driver-storage-rbd-debuginfo-0:6.0.0-28.module+el8.3.0+7827+5e65edd7.x86_64
    - libvirt-daemon-driver-storage-scsi-0:6.0.0-28.module+el8.3.0+7827+5e65edd7.x86_64
    - libvirt-daemon-driver-storage-scsi-debuginfo-0:6.0.0-28.module+el8.3.0+7827+5e65edd7.x86_64
    - libvirt-daemon-kvm-0:6.0.0-28.module+el8.3.0+7827+5e65edd7.x86_64
    - libvirt-dbus-0:1.3.0-2.module+el8.3.0+6423+e4cb6418.src
    - libvirt-dbus-0:1.3.0-2.module+el8.3.0+6423+e4cb6418.x86_64
    - libvirt-dbus-debuginfo-0:1.3.0-2.module+el8.3.0+6423+e4cb6418.x86_64
    - libvirt-dbus-debugsource-0:1.3.0-2.module+el8.3.0+6423+e4cb6418.x86_64
    - libvirt-debuginfo-0:6.0.0-28.module+el8.3.0+7827+5e65edd7.x86_64
    - libvirt-debugsource-0:6.0.0-28.module+el8.3.0+7827+5e65edd7.x86_64
    - libvirt-devel-0:6.0.0-28.module+el8.3.0+7827+5e65edd7.x86_64
    - libvirt-docs-0:6.0.0-28.module+el8.3.0+7827+5e65edd7.x86_64
    - libvirt-libs-0:6.0.0-28.module+el8.3.0+7827+5e65edd7.x86_64
    - libvirt-libs-debuginfo-0:6.0.0-28.module+el8.3.0+7827+5e65edd7.x86_64
    - libvirt-lock-sanlock-0:6.0.0-28.module+el8.3.0+7827+5e65edd7.x86_64
    - libvirt-lock-sanlock-debuginfo-0:6.0.0-28.module+el8.3.0+7827+5e65edd7.x86_64
    - libvirt-nss-0:6.0.0-28.module+el8.3.0+7827+5e65edd7.x86_64
    - libvirt-nss-debuginfo-0:6.0.0-28.module+el8.3.0+7827+5e65edd7.x86_64
    - libvirt-python-0:6.0.0-1.module+el8.3.0+6423+e4cb6418.src
    - libvirt-python-debugsource-0:6.0.0-1.module+el8.3.0+6423+e4cb6418.x86_64
    - lua-guestfs-1:1.40.2-25.module+el8.3.0+7421+642fe24f.x86_64
    - lua-guestfs-debuginfo-1:1.40.2-25.module+el8.3.0+7421+642fe24f.x86_64
    - nbdfuse-0:1.2.2-1.module+el8.3.0+7353+9de0a3cc.x86_64
    - nbdfuse-debuginfo-0:1.2.2-1.module+el8.3.0+7353+9de0a3cc.x86_64
    - nbdkit-0:1.16.2-4.module+el8.3.0+6922+fd575af8.src
    - nbdkit-0:1.16.2-4.module+el8.3.0+6922+fd575af8.x86_64
    - nbdkit-bash-completion-0:1.16.2-4.module+el8.3.0+6922+fd575af8.noarch
    - nbdkit-basic-filters-0:1.16.2-4.module+el8.3.0+6922+fd575af8.x86_64
    - nbdkit-basic-filters-debuginfo-0:1.16.2-4.module+el8.3.0+6922+fd575af8.x86_64
    - nbdkit-basic-plugins-0:1.16.2-4.module+el8.3.0+6922+fd575af8.x86_64
    - nbdkit-basic-plugins-debuginfo-0:1.16.2-4.module+el8.3.0+6922+fd575af8.x86_64
    - nbdkit-curl-plugin-0:1.16.2-4.module+el8.3.0+6922+fd575af8.x86_64
    - nbdkit-curl-plugin-debuginfo-0:1.16.2-4.module+el8.3.0+6922+fd575af8.x86_64
    - nbdkit-debuginfo-0:1.16.2-4.module+el8.3.0+6922+fd575af8.x86_64
    - nbdkit-debugsource-0:1.16.2-4.module+el8.3.0+6922+fd575af8.x86_64
    - nbdkit-devel-0:1.16.2-4.module+el8.3.0+6922+fd575af8.x86_64
    - nbdkit-example-plugins-0:1.16.2-4.module+el8.3.0+6922+fd575af8.x86_64
    - nbdkit-example-plugins-debuginfo-0:1.16.2-4.module+el8.3.0+6922+fd575af8.x86_64
    - nbdkit-gzip-plugin-0:1.16.2-4.module+el8.3.0+6922+fd575af8.x86_64
    - nbdkit-gzip-plugin-debuginfo-0:1.16.2-4.module+el8.3.0+6922+fd575af8.x86_64
    - nbdkit-linuxdisk-plugin-0:1.16.2-4.module+el8.3.0+6922+fd575af8.x86_64
    - nbdkit-linuxdisk-plugin-debuginfo-0:1.16.2-4.module+el8.3.0+6922+fd575af8.x86_64
    - nbdkit-python-plugin-0:1.16.2-4.module+el8.3.0+6922+fd575af8.x86_64
    - nbdkit-python-plugin-debuginfo-0:1.16.2-4.module+el8.3.0+6922+fd575af8.x86_64
    - nbdkit-server-0:1.16.2-4.module+el8.3.0+6922+fd575af8.x86_64
    - nbdkit-server-debuginfo-0:1.16.2-4.module+el8.3.0+6922+fd575af8.x86_64
    - nbdkit-ssh-plugin-0:1.16.2-4.module+el8.3.0+6922+fd575af8.x86_64
    - nbdkit-ssh-plugin-debuginfo-0:1.16.2-4.module+el8.3.0+6922+fd575af8.x86_64
    - nbdkit-vddk-plugin-0:1.16.2-4.module+el8.3.0+6922+fd575af8.x86_64
    - nbdkit-vddk-plugin-debuginfo-0:1.16.2-4.module+el8.3.0+6922+fd575af8.x86_64
    - nbdkit-xz-filter-0:1.16.2-4.module+el8.3.0+6922+fd575af8.x86_64
    - nbdkit-xz-filter-debuginfo-0:1.16.2-4.module+el8.3.0+6922+fd575af8.x86_64
    - netcf-0:0.2.8-12.module+el8.1.0+4066+0f1aadab.src
    - netcf-0:0.2.8-12.module+el8.1.0+4066+0f1aadab.x86_64
    - netcf-debuginfo-0:0.2.8-12.module+el8.1.0+4066+0f1aadab.x86_64
    - netcf-debugsource-0:0.2.8-12.module+el8.1.0+4066+0f1aadab.x86_64
    - netcf-devel-0:0.2.8-12.module+el8.1.0+4066+0f1aadab.x86_64
    - netcf-libs-0:0.2.8-12.module+el8.1.0+4066+0f1aadab.x86_64
    - netcf-libs-debuginfo-0:0.2.8-12.module+el8.1.0+4066+0f1aadab.x86_64
    - perl-Sys-Guestfs-1:1.40.2-25.module+el8.3.0+7421+642fe24f.x86_64
    - perl-Sys-Guestfs-debuginfo-1:1.40.2-25.module+el8.3.0+7421+642fe24f.x86_64
    - perl-Sys-Virt-0:6.0.0-1.module+el8.3.0+6423+e4cb6418.src
    - perl-Sys-Virt-0:6.0.0-1.module+el8.3.0+6423+e4cb6418.x86_64
    - perl-Sys-Virt-debuginfo-0:6.0.0-1.module+el8.3.0+6423+e4cb6418.x86_64
    - perl-Sys-Virt-debugsource-0:6.0.0-1.module+el8.3.0+6423+e4cb6418.x86_64
    - perl-hivex-0:1.3.18-20.module+el8.3.0+6423+e4cb6418.x86_64
    - perl-hivex-debuginfo-0:1.3.18-20.module+el8.3.0+6423+e4cb6418.x86_64
    - python3-hivex-0:1.3.18-20.module+el8.3.0+6423+e4cb6418.x86_64
    - python3-hivex-debuginfo-0:1.3.18-20.module+el8.3.0+6423+e4cb6418.x86_64
    - python3-libguestfs-1:1.40.2-25.module+el8.3.0+7421+642fe24f.x86_64
    - python3-libguestfs-debuginfo-1:1.40.2-25.module+el8.3.0+7421+642fe24f.x86_64
    - python3-libnbd-0:1.2.2-1.module+el8.3.0+7353+9de0a3cc.x86_64
    - python3-libnbd-debuginfo-0:1.2.2-1.module+el8.3.0+7353+9de0a3cc.x86_64
    - python3-libvirt-0:6.0.0-1.module+el8.3.0+6423+e4cb6418.x86_64
    - python3-libvirt-debuginfo-0:6.0.0-1.module+el8.3.0+6423+e4cb6418.x86_64
    - qemu-guest-agent-15:4.2.0-34.module+el8.3.0+9903+ca3e42fb.4.x86_64
    - qemu-guest-agent-debuginfo-15:4.2.0-34.module+el8.3.0+9903+ca3e42fb.4.x86_64
    - qemu-img-15:4.2.0-34.module+el8.3.0+9903+ca3e42fb.4.x86_64
    - qemu-img-debuginfo-15:4.2.0-34.module+el8.3.0+9903+ca3e42fb.4.x86_64
    - qemu-kvm-15:4.2.0-34.module+el8.3.0+9903+ca3e42fb.4.src
    - qemu-kvm-15:4.2.0-34.module+el8.3.0+9903+ca3e42fb.4.x86_64
    - qemu-kvm-block-curl-15:4.2.0-34.module+el8.3.0+9903+ca3e42fb.4.x86_64
    - qemu-kvm-block-curl-debuginfo-15:4.2.0-34.module+el8.3.0+9903+ca3e42fb.4.x86_64
    - qemu-kvm-block-gluster-15:4.2.0-34.module+el8.3.0+9903+ca3e42fb.4.x86_64
    - qemu-kvm-block-gluster-debuginfo-15:4.2.0-34.module+el8.3.0+9903+ca3e42fb.4.x86_64
    - qemu-kvm-block-iscsi-15:4.2.0-34.module+el8.3.0+9903+ca3e42fb.4.x86_64
    - qemu-kvm-block-iscsi-debuginfo-15:4.2.0-34.module+el8.3.0+9903+ca3e42fb.4.x86_64
    - qemu-kvm-block-rbd-15:4.2.0-34.module+el8.3.0+9903+ca3e42fb.4.x86_64
    - qemu-kvm-block-rbd-debuginfo-15:4.2.0-34.module+el8.3.0+9903+ca3e42fb.4.x86_64
    - qemu-kvm-block-ssh-15:4.2.0-34.module+el8.3.0+9903+ca3e42fb.4.x86_64
    - qemu-kvm-block-ssh-debuginfo-15:4.2.0-34.module+el8.3.0+9903+ca3e42fb.4.x86_64
    - qemu-kvm-common-15:4.2.0-34.module+el8.3.0+9903+ca3e42fb.4.x86_64
    - qemu-kvm-common-debuginfo-15:4.2.0-34.module+el8.3.0+9903+ca3e42fb.4.x86_64
    - qemu-kvm-core-15:4.2.0-34.module+el8.3.0+9903+ca3e42fb.4.x86_64
    - qemu-kvm-core-debuginfo-15:4.2.0-34.module+el8.3.0+9903+ca3e42fb.4.x86_64
    - qemu-kvm-debuginfo-15:4.2.0-34.module+el8.3.0+9903+ca3e42fb.4.x86_64
    - qemu-kvm-debugsource-15:4.2.0-34.module+el8.3.0+9903+ca3e42fb.4.x86_64
    - ruby-hivex-0:1.3.18-20.module+el8.3.0+6423+e4cb6418.x86_64
    - ruby-hivex-debuginfo-0:1.3.18-20.module+el8.3.0+6423+e4cb6418.x86_64
    - ruby-libguestfs-1:1.40.2-25.module+el8.3.0+7421+642fe24f.x86_64
    - ruby-libguestfs-debuginfo-1:1.40.2-25.module+el8.3.0+7421+642fe24f.x86_64
    - seabios-0:1.13.0-2.module+el8.3.0+7353+9de0a3cc.src
    - seabios-0:1.13.0-2.module+el8.3.0+7353+9de0a3cc.x86_64
    - seabios-bin-0:1.13.0-2.module+el8.3.0+7353+9de0a3cc.noarch
    - seavgabios-bin-0:1.13.0-2.module+el8.3.0+7353+9de0a3cc.noarch
    - sgabios-1:0.20170427git-3.module+el8.1.0+4066+0f1aadab.src
    - sgabios-1:0.20170427git-3.module+el8.1.0+4066+0f1aadab.x86_64
    - sgabios-bin-1:0.20170427git-3.module+el8.1.0+4066+0f1aadab.noarch
    - supermin-0:5.1.19-10.module+el8.3.0+6423+e4cb6418.src
    - supermin-0:5.1.19-10.module+el8.3.0+6423+e4cb6418.x86_64
    - supermin-debuginfo-0:5.1.19-10.module+el8.3.0+6423+e4cb6418.x86_64
    - supermin-debugsource-0:5.1.19-10.module+el8.3.0+6423+e4cb6418.x86_64
    - supermin-devel-0:5.1.19-10.module+el8.3.0+6423+e4cb6418.x86_64
    - virt-dib-1:1.40.2-25.module+el8.3.0+7421+642fe24f.x86_64
    - virt-dib-debuginfo-1:1.40.2-25.module+el8.3.0+7421+642fe24f.x86_64
    - virt-v2v-1:1.40.2-25.module+el8.3.0+7421+642fe24f.x86_64
    - virt-v2v-debuginfo-1:1.40.2-25.module+el8.3.0+7421+642fe24f.x86_64
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
    - SLOF-0:20191022-3.git899d9883.module+el8.3.0+6423+e4cb6418.src
    - hivex-0:1.3.18-20.module+el8.3.0+6423+e4cb6418.i686
    - hivex-debuginfo-0:1.3.18-20.module+el8.3.0+6423+e4cb6418.i686
    - hivex-debugsource-0:1.3.18-20.module+el8.3.0+6423+e4cb6418.i686
    - hivex-devel-0:1.3.18-20.module+el8.3.0+6423+e4cb6418.i686
    - libguestfs-winsupport-0:8.2-1.module+el8.3.0+6423+e4cb6418.i686
    - libiscsi-0:1.18.0-8.module+el8.1.0+4066+0f1aadab.i686
    - libiscsi-debuginfo-0:1.18.0-8.module+el8.1.0+4066+0f1aadab.i686
    - libiscsi-debugsource-0:1.18.0-8.module+el8.1.0+4066+0f1aadab.i686
    - libiscsi-devel-0:1.18.0-8.module+el8.1.0+4066+0f1aadab.i686
    - libiscsi-utils-0:1.18.0-8.module+el8.1.0+4066+0f1aadab.i686
    - libiscsi-utils-debuginfo-0:1.18.0-8.module+el8.1.0+4066+0f1aadab.i686
    - libnbd-0:1.2.2-1.module+el8.3.0+7353+9de0a3cc.i686
    - libnbd-debuginfo-0:1.2.2-1.module+el8.3.0+7353+9de0a3cc.i686
    - libnbd-debugsource-0:1.2.2-1.module+el8.3.0+7353+9de0a3cc.i686
    - libnbd-devel-0:1.2.2-1.module+el8.3.0+7353+9de0a3cc.i686
    - libvirt-0:6.0.0-28.module+el8.3.0+7827+5e65edd7.i686
    - libvirt-admin-0:6.0.0-28.module+el8.3.0+7827+5e65edd7.i686
    - libvirt-admin-debuginfo-0:6.0.0-28.module+el8.3.0+7827+5e65edd7.i686
    - libvirt-bash-completion-0:6.0.0-28.module+el8.3.0+7827+5e65edd7.i686
    - libvirt-client-0:6.0.0-28.module+el8.3.0+7827+5e65edd7.i686
    - libvirt-client-debuginfo-0:6.0.0-28.module+el8.3.0+7827+5e65edd7.i686
    - libvirt-daemon-0:6.0.0-28.module+el8.3.0+7827+5e65edd7.i686
    - libvirt-daemon-config-network-0:6.0.0-28.module+el8.3.0+7827+5e65edd7.i686
    - libvirt-daemon-config-nwfilter-0:6.0.0-28.module+el8.3.0+7827+5e65edd7.i686
    - libvirt-daemon-debuginfo-0:6.0.0-28.module+el8.3.0+7827+5e65edd7.i686
    - libvirt-daemon-driver-interface-0:6.0.0-28.module+el8.3.0+7827+5e65edd7.i686
    - libvirt-daemon-driver-interface-debuginfo-0:6.0.0-28.module+el8.3.0+7827+5e65edd7.i686
    - libvirt-daemon-driver-network-0:6.0.0-28.module+el8.3.0+7827+5e65edd7.i686
    - libvirt-daemon-driver-network-debuginfo-0:6.0.0-28.module+el8.3.0+7827+5e65edd7.i686
    - libvirt-daemon-driver-nodedev-0:6.0.0-28.module+el8.3.0+7827+5e65edd7.i686
    - libvirt-daemon-driver-nodedev-debuginfo-0:6.0.0-28.module+el8.3.0+7827+5e65edd7.i686
    - libvirt-daemon-driver-nwfilter-0:6.0.0-28.module+el8.3.0+7827+5e65edd7.i686
    - libvirt-daemon-driver-nwfilter-debuginfo-0:6.0.0-28.module+el8.3.0+7827+5e65edd7.i686
    - libvirt-daemon-driver-secret-0:6.0.0-28.module+el8.3.0+7827+5e65edd7.i686
    - libvirt-daemon-driver-secret-debuginfo-0:6.0.0-28.module+el8.3.0+7827+5e65edd7.i686
    - libvirt-daemon-driver-storage-0:6.0.0-28.module+el8.3.0+7827+5e65edd7.i686
    - libvirt-daemon-driver-storage-core-0:6.0.0-28.module+el8.3.0+7827+5e65edd7.i686
    - libvirt-daemon-driver-storage-core-debuginfo-0:6.0.0-28.module+el8.3.0+7827+5e65edd7.i686
    - libvirt-daemon-driver-storage-disk-0:6.0.0-28.module+el8.3.0+7827+5e65edd7.i686
    - libvirt-daemon-driver-storage-disk-debuginfo-0:6.0.0-28.module+el8.3.0+7827+5e65edd7.i686
    - libvirt-daemon-driver-storage-iscsi-0:6.0.0-28.module+el8.3.0+7827+5e65edd7.i686
    - libvirt-daemon-driver-storage-iscsi-debuginfo-0:6.0.0-28.module+el8.3.0+7827+5e65edd7.i686
    - libvirt-daemon-driver-storage-iscsi-direct-0:6.0.0-28.module+el8.3.0+7827+5e65edd7.i686
    - libvirt-daemon-driver-storage-iscsi-direct-debuginfo-0:6.0.0-28.module+el8.3.0+7827+5e65edd7.i686
    - libvirt-daemon-driver-storage-logical-0:6.0.0-28.module+el8.3.0+7827+5e65edd7.i686
    - libvirt-daemon-driver-storage-logical-debuginfo-0:6.0.0-28.module+el8.3.0+7827+5e65edd7.i686
    - libvirt-daemon-driver-storage-mpath-0:6.0.0-28.module+el8.3.0+7827+5e65edd7.i686
    - libvirt-daemon-driver-storage-mpath-debuginfo-0:6.0.0-28.module+el8.3.0+7827+5e65edd7.i686
    - libvirt-daemon-driver-storage-rbd-0:6.0.0-28.module+el8.3.0+7827+5e65edd7.i686
    - libvirt-daemon-driver-storage-rbd-debuginfo-0:6.0.0-28.module+el8.3.0+7827+5e65edd7.i686
    - libvirt-daemon-driver-storage-scsi-0:6.0.0-28.module+el8.3.0+7827+5e65edd7.i686
    - libvirt-daemon-driver-storage-scsi-debuginfo-0:6.0.0-28.module+el8.3.0+7827+5e65edd7.i686
    - libvirt-dbus-0:1.3.0-2.module+el8.3.0+6423+e4cb6418.i686
    - libvirt-dbus-debuginfo-0:1.3.0-2.module+el8.3.0+6423+e4cb6418.i686
    - libvirt-dbus-debugsource-0:1.3.0-2.module+el8.3.0+6423+e4cb6418.i686
    - libvirt-debuginfo-0:6.0.0-28.module+el8.3.0+7827+5e65edd7.i686
    - libvirt-debugsource-0:6.0.0-28.module+el8.3.0+7827+5e65edd7.i686
    - libvirt-devel-0:6.0.0-28.module+el8.3.0+7827+5e65edd7.i686
    - libvirt-docs-0:6.0.0-28.module+el8.3.0+7827+5e65edd7.i686
    - libvirt-libs-0:6.0.0-28.module+el8.3.0+7827+5e65edd7.i686
    - libvirt-libs-debuginfo-0:6.0.0-28.module+el8.3.0+7827+5e65edd7.i686
    - libvirt-nss-0:6.0.0-28.module+el8.3.0+7827+5e65edd7.i686
    - libvirt-nss-debuginfo-0:6.0.0-28.module+el8.3.0+7827+5e65edd7.i686
    - libvirt-python-debugsource-0:6.0.0-1.module+el8.3.0+6423+e4cb6418.i686
    - nbdfuse-0:1.2.2-1.module+el8.3.0+7353+9de0a3cc.i686
    - nbdfuse-debuginfo-0:1.2.2-1.module+el8.3.0+7353+9de0a3cc.i686
    - netcf-0:0.2.8-12.module+el8.1.0+4066+0f1aadab.i686
    - netcf-debuginfo-0:0.2.8-12.module+el8.1.0+4066+0f1aadab.i686
    - netcf-debugsource-0:0.2.8-12.module+el8.1.0+4066+0f1aadab.i686
    - netcf-devel-0:0.2.8-12.module+el8.1.0+4066+0f1aadab.i686
    - netcf-libs-0:0.2.8-12.module+el8.1.0+4066+0f1aadab.i686
    - netcf-libs-debuginfo-0:0.2.8-12.module+el8.1.0+4066+0f1aadab.i686
    - ocaml-hivex-0:1.3.18-20.module+el8.3.0+6423+e4cb6418.i686
    - ocaml-hivex-0:1.3.18-20.module+el8.3.0+6423+e4cb6418.x86_64
    - ocaml-hivex-debuginfo-0:1.3.18-20.module+el8.3.0+6423+e4cb6418.i686
    - ocaml-hivex-debuginfo-0:1.3.18-20.module+el8.3.0+6423+e4cb6418.x86_64
    - ocaml-hivex-devel-0:1.3.18-20.module+el8.3.0+6423+e4cb6418.i686
    - ocaml-hivex-devel-0:1.3.18-20.module+el8.3.0+6423+e4cb6418.x86_64
    - ocaml-libguestfs-1:1.40.2-25.module+el8.3.0+7421+642fe24f.x86_64
    - ocaml-libguestfs-debuginfo-1:1.40.2-25.module+el8.3.0+7421+642fe24f.x86_64
    - ocaml-libguestfs-devel-1:1.40.2-25.module+el8.3.0+7421+642fe24f.x86_64
    - ocaml-libnbd-0:1.2.2-1.module+el8.3.0+7353+9de0a3cc.i686
    - ocaml-libnbd-0:1.2.2-1.module+el8.3.0+7353+9de0a3cc.x86_64
    - ocaml-libnbd-debuginfo-0:1.2.2-1.module+el8.3.0+7353+9de0a3cc.i686
    - ocaml-libnbd-debuginfo-0:1.2.2-1.module+el8.3.0+7353+9de0a3cc.x86_64
    - ocaml-libnbd-devel-0:1.2.2-1.module+el8.3.0+7353+9de0a3cc.i686
    - ocaml-libnbd-devel-0:1.2.2-1.module+el8.3.0+7353+9de0a3cc.x86_64
    - perl-Sys-Virt-0:6.0.0-1.module+el8.3.0+6423+e4cb6418.i686
    - perl-Sys-Virt-debuginfo-0:6.0.0-1.module+el8.3.0+6423+e4cb6418.i686
    - perl-Sys-Virt-debugsource-0:6.0.0-1.module+el8.3.0+6423+e4cb6418.i686
    - perl-hivex-0:1.3.18-20.module+el8.3.0+6423+e4cb6418.i686
    - perl-hivex-debuginfo-0:1.3.18-20.module+el8.3.0+6423+e4cb6418.i686
    - python3-hivex-0:1.3.18-20.module+el8.3.0+6423+e4cb6418.i686
    - python3-hivex-debuginfo-0:1.3.18-20.module+el8.3.0+6423+e4cb6418.i686
    - python3-libnbd-0:1.2.2-1.module+el8.3.0+7353+9de0a3cc.i686
    - python3-libnbd-debuginfo-0:1.2.2-1.module+el8.3.0+7353+9de0a3cc.i686
    - python3-libvirt-0:6.0.0-1.module+el8.3.0+6423+e4cb6418.i686
    - python3-libvirt-debuginfo-0:6.0.0-1.module+el8.3.0+6423+e4cb6418.i686
    - qemu-kvm-tests-15:4.2.0-34.module+el8.3.0+9903+ca3e42fb.4.x86_64
    - qemu-kvm-tests-debuginfo-15:4.2.0-34.module+el8.3.0+9903+ca3e42fb.4.x86_64
    - ruby-hivex-0:1.3.18-20.module+el8.3.0+6423+e4cb6418.i686
    - ruby-hivex-debuginfo-0:1.3.18-20.module+el8.3.0+6423+e4cb6418.i686
    - sgabios-1:0.20170427git-3.module+el8.1.0+4066+0f1aadab.i686
...
    """

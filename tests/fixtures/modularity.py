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
def multilib_ruby_with_artifacts():
    return """
---
document: modulemd
version: 2
data:
  name: ruby
  stream: "3.1"
  version: 9010020221019142933
  context: 8cf767d6
  arch: x86_64
  summary: An interpreter of object-oriented scripting language
  description: >-
    Ruby is the interpreted scripting language for quick and easy object-oriented
    programming.  It has many features to process text files and to do system management
    tasks (as in Perl).  It is simple, straight-forward, and extensible.
  license:
    module:
    - MIT
  dependencies:
  - buildrequires:
      platform: [el8]
    requires:
      platform: [el8]
  references:
    community: http://ruby-lang.org/
    documentation: https://www.ruby-lang.org/en/documentation/
    tracker: https://bugs.ruby-lang.org/
  profiles:
    common:
      rpms:
      - ruby
  api:
    rpms:
    - ruby
    - ruby-bundled-gems
    - ruby-default-gems
    - ruby-devel
    - ruby-libs
    - rubygem-bigdecimal
    - rubygem-bundler
    - rubygem-io-console
    - rubygem-irb
    - rubygem-json
    - rubygem-minitest
    - rubygem-mysql2
    - rubygem-pg
    - rubygem-power_assert
    - rubygem-psych
    - rubygem-rake
    - rubygem-rbs
    - rubygem-rdoc
    - rubygem-rexml
    - rubygem-rss
    - rubygem-test-unit
    - rubygem-typeprof
    - rubygems
    - rubygems-devel
  components:
    rpms:
      ruby:
        rationale: An interpreter of object-oriented scripting language
        ref: 4f1e5e9f48df872a4595494f58bfc3eb8a9b7a31
        buildorder: 101
        arches: [aarch64, i686, ppc64le, s390x, x86_64]
        multilib: [x86_64]
      rubygem-mysql2:
        rationale: A simple, fast Mysql library for Ruby, binding to libmysql
        ref: e8b82bc12045089bbdb262c6ef4bb610d187c707
        buildorder: 102
        arches: [aarch64, i686, ppc64le, s390x, x86_64]
      rubygem-pg:
        rationale: A Ruby interface to the PostgreSQL RDBMS
        ref: c65bdee50421e88eb4042cdffa712ddaac9ff11b
        buildorder: 102
        arches: [aarch64, i686, ppc64le, s390x, x86_64]
  artifacts:
    rpms:
    - ruby-0:3.1.2-141.module_el8.1.0+8+503f6fbd.i686
    - ruby-0:3.1.2-141.module_el8.1.0+8+503f6fbd.src
    - ruby-0:3.1.2-141.module_el8.1.0+8+503f6fbd.x86_64
    - ruby-debuginfo-0:3.1.2-141.module_el8.1.0+8+503f6fbd.i686
    - ruby-debuginfo-0:3.1.2-141.module_el8.1.0+8+503f6fbd.x86_64
    - ruby-debugsource-0:3.1.2-141.module_el8.1.0+8+503f6fbd.i686
    - ruby-debugsource-0:3.1.2-141.module_el8.1.0+8+503f6fbd.x86_64
    - ruby-devel-0:3.1.2-141.module_el8.1.0+8+503f6fbd.i686
    - ruby-devel-0:3.1.2-141.module_el8.1.0+8+503f6fbd.x86_64
    - rubygem-pg-0:1.3.5-1.module_el8.1.0+8+503f6fbd.src
    - rubygem-pg-1.3.5-0:1-141.module_el8.1.0+8+503f6fbd.x86_64
    - rubygem-pg-debuginfo-0:3.1.2-141.module_el8.1.0+8+503f6fbd.x86_64
    - rubygem-pg-debugsource-0:3.1.2-141.module_el8.1.0+8+503f6fbd.x86_64
    - rubygem-pg-doc-0:3.3.7-141.module_el8.1.0+8+503f6fbd.noarch
    - rubygems-0:3.3.7-141.module_el8.1.0+8+503f6fbd.noarch
    - rubygems-devel-0:3.3.7-141.module_el8.1.0+8+503f6fbd.noarch
...
---
document: modulemd
version: 2
data:
  name: ruby-devel
  stream: "3.1"
  version: 9010020221019142933
  context: 8cf767d6
  arch: x86_64
  summary: An interpreter of object-oriented scripting language
  description: >-
    Ruby is the interpreted scripting language for quick and easy object-oriented
    programming.  It has many features to process text files and to do system management
    tasks (as in Perl).  It is simple, straight-forward, and extensible.
  license:
    module:
    - MIT
  dependencies:
  - buildrequires:
      platform: [el8]
    requires:
      platform: [el8]
  references:
    community: http://ruby-lang.org/
    documentation: https://www.ruby-lang.org/en/documentation/
    tracker: https://bugs.ruby-lang.org/
  profiles:
    common:
      rpms:
      - ruby
  api:
    rpms:
    - ruby
    - ruby-bundled-gems
    - ruby-default-gems
    - ruby-devel
    - ruby-libs
    - rubygem-bigdecimal
    - rubygem-bundler
    - rubygem-io-console
    - rubygem-irb
    - rubygem-json
    - rubygem-minitest
    - rubygem-mysql2
    - rubygem-pg
    - rubygem-power_assert
    - rubygem-psych
    - rubygem-rake
    - rubygem-rbs
    - rubygem-rdoc
    - rubygem-rexml
    - rubygem-rss
    - rubygem-test-unit
    - rubygem-typeprof
    - rubygems
    - rubygems-devel
  components:
    rpms:
      ruby:
        rationale: An interpreter of object-oriented scripting language
        ref: 4f1e5e9f48df872a4595494f58bfc3eb8a9b7a31
        buildorder: 101
        arches: [aarch64, i686, ppc64le, s390x, x86_64]
        multilib: [x86_64]
      rubygem-mysql2:
        rationale: A simple, fast Mysql library for Ruby, binding to libmysql
        ref: e8b82bc12045089bbdb262c6ef4bb610d187c707
        buildorder: 102
        arches: [aarch64, i686, ppc64le, s390x, x86_64]
      rubygem-pg:
        rationale: A Ruby interface to the PostgreSQL RDBMS
        ref: c65bdee50421e88eb4042cdffa712ddaac9ff11b
        buildorder: 102
        arches: [aarch64, i686, ppc64le, s390x, x86_64]
...
"""


@pytest.fixture
def multilib_subversion_with_artifacts():
    return """
---
document: modulemd
version: 2
data:
  name: subversion
  stream: "1.10"
  version: 8060020221109095619
  context: a51370e3
  arch: x86_64
  summary: Apache Subversion
  description: >-
    Apache Subversion, a Modern Version Control System
  license:
    module:
    - MIT
  dependencies:
  - buildrequires:
      httpd: [2.4]
      platform: [el8]
      swig: [3.0]
    requires:
      platform: [el8]
  references:
    documentation: http://subversion.apache.org/docs/
    tracker: https://issues.apache.org/jira/projects/SVN
  profiles:
    common:
      rpms:
      - subversion
      - subversion-libs
      - subversion-tools
    server:
      rpms:
      - mod_dav_svn
      - subversion
      - subversion-libs
      - subversion-tools
  api:
    rpms:
    - mod_dav_svn
    - subversion
    - subversion-devel
    - subversion-libs
  filter:
    rpms:
    - libserf-devel
    - python3-subversion
    - subversion-ruby
    - utf8proc-devel
  buildopts:
    rpms:
      macros: >
        %_without_kwallet 1
        %_without_python2 1
        %_with_python3 1
        %_without_bdb 1
        %_without_pyswig 1
  components:
    rpms:
      libserf:
        rationale: Build dependency.
        ref: 6ebf0093af090cf5c8d082e04ba3d028458e0f54
        buildorder: 10
        arches: [aarch64, i686, ppc64le, s390x, x86_64]
      subversion:
        rationale: Module API.
        ref: a757409c2fc92983ed4ba21058e47f22941be59e
        buildorder: 20
        arches: [aarch64, i686, ppc64le, s390x, x86_64]
      utf8proc:
        rationale: Build dependency.
        ref: 3a752429dbff2f4dc394a579715b23253339d776
        buildorder: 10
        arches: [aarch64, i686, ppc64le, s390x, x86_64]
  artifacts:
    rpms:
    - subversion-0:1.10.2-5.module_el8.6.0+3347+66c1e1d6.src
    - subversion-0:1.10.2-5.module_el8.6.0+3347+66c1e1d6.x86_64
    - subversion-debuginfo-0:1.10.2-5.module_el8.6.0+3347+66c1e1d6.x86_64
    - subversion-debugsource-0:1.10.2-5.module_el8.6.0+3347+66c1e1d6.x86_64
    - subversion-devel-0:1.10.2-5.module_el8.6.0+3347+66c1e1d6.x86_64
...
---
document: modulemd
version: 2
data:
  name: subversion-devel
  stream: "1.10"
  version: 8060020221109095619
  context: a51370e3
  arch: x86_64
  summary: Apache Subversion
  description: >-
    Apache Subversion, a Modern Version Control System
  license:
    module:
    - MIT
  dependencies:
  - buildrequires:
      httpd: [2.4]
      platform: [el8]
      swig: [3.0]
    requires:
      platform: [el8]
  references:
    documentation: http://subversion.apache.org/docs/
    tracker: https://issues.apache.org/jira/projects/SVN
  profiles:
    common:
      rpms:
      - subversion
      - subversion-libs
      - subversion-tools
    server:
      rpms:
      - mod_dav_svn
      - subversion
      - subversion-libs
      - subversion-tools
  api:
    rpms:
    - mod_dav_svn
    - subversion
    - subversion-devel
    - subversion-libs
  filter:
    rpms:
    - libserf-devel
    - python3-subversion
    - subversion-ruby
    - utf8proc-devel
  buildopts:
    rpms:
      macros: >
        %_without_kwallet 1
        %_without_python2 1
        %_with_python3 1
        %_without_bdb 1
        %_without_pyswig 1
  components:
    rpms:
      libserf:
        rationale: Build dependency.
        ref: 6ebf0093af090cf5c8d082e04ba3d028458e0f54
        buildorder: 10
        arches: [aarch64, i686, ppc64le, s390x, x86_64]
      subversion:
        rationale: Module API.
        ref: a757409c2fc92983ed4ba21058e47f22941be59e
        buildorder: 20
        arches: [aarch64, i686, ppc64le, s390x, x86_64]
      utf8proc:
        rationale: Build dependency.
        ref: 3a752429dbff2f4dc394a579715b23253339d776
        buildorder: 10
        arches: [aarch64, i686, ppc64le, s390x, x86_64]
  artifacts:
    rpms:
    - subversion-0:1.10.2-5.module_el8.6.0+3347+66c1e1d6.i686
    - subversion-debuginfo-0:1.10.2-5.module_el8.6.0+3347+66c1e1d6.i686
    - subversion-debugsource-0:1.10.2-5.module_el8.6.0+3347+66c1e1d6.i686
    - subversion-devel-0:1.10.2-5.module_el8.6.0+3347+66c1e1d6.i686
    - subversion-ruby-0:1.10.2-5.module_el8.6.0+3347+66c1e1d6.i686
    - subversion-ruby-0:1.10.2-5.module_el8.6.0+3347+66c1e1d6.x86_64
...
"""


@pytest.fixture
def multilib_llvm_with_artifacts():
    return """
---
document: modulemd
version: 2
data:
  name: llvm-toolset
  stream: "rhel8"
  version: 8060020220204053142
  context: d63f516d
  arch: x86_64
  summary: LLVM
  description: >-
    LLVM Tools and libraries
  license:
    module:
    - MIT
    content:
    - NCSA
    - NCSA and MIT
    - NCSA or MIT
  xmd: {}
  dependencies:
  - buildrequires:
      platform: [el8.6.0]
    requires:
      platform: [el8]
  profiles:
    common:
      rpms:
      - llvm-toolset
  api:
    rpms:
    - clang
    - clang-analyzer
    - clang-devel
    - clang-libs
    - clang-tools-extra
    - git-clang-format
    - lld
    - lld-libs
    - lldb
    - lldb-devel
    - llvm
    - llvm-devel
    - llvm-libs
  components:
    rpms:
      clang:
        rationale: clang tools and libraries
        ref: stream-rhel-8-rhel-8.6.0
        buildorder: 1
        arches: [aarch64, i686, ppc64le, s390x, x86_64]
        multilib: [x86_64]
      compiler-rt:
        rationale: LLVM compiler intrinsic and sanitizer libraries
        ref: stream-rhel-8-rhel-8.6.0
        buildorder: 1
        arches: [aarch64, i686, ppc64le, s390x, x86_64]
        multilib: [x86_64]
      libomp:
        rationale: LLVM OpenMP runtime
        ref: stream-rhel-8-rhel-8.6.0
        buildorder: 2
        arches: [aarch64, i686, ppc64le, s390x, x86_64]
        multilib: [x86_64]
      lld:
        rationale: LLVM linker
        ref: stream-rhel-8-rhel-8.6.0
        buildorder: 1
        arches: [aarch64, i686, ppc64le, s390x, x86_64]
        multilib: [x86_64]
      lldb:
        rationale: lldb debugger
        ref: stream-rhel-8-rhel-8.6.0
        buildorder: 2
        arches: [aarch64, i686, ppc64le, s390x, x86_64]
        multilib: [x86_64]
      llvm:
        rationale: LLVM tools and libraries
        ref: stream-rhel-8-rhel-8.6.0
        arches: [aarch64, i686, ppc64le, s390x, x86_64]
        multilib: [x86_64]
      python-lit:
        rationale: Lit test runner for LLVM
        ref: stream-rhel-8-rhel-8.6.0
        arches: [aarch64, i686, ppc64le, s390x, x86_64]
  artifacts:
    rpms:
    - clang-0:13.0.1-1.module+el8.6.0+14118+d530a951.i686
    - clang-0:13.0.1-1.module+el8.6.0+14118+d530a951.src
    - clang-0:13.0.1-1.module+el8.6.0+14118+d530a951.x86_64
    - compiler-rt-0:13.0.1-1.module+el8.6.0+14118+d530a951.i686
    - compiler-rt-0:13.0.1-1.module+el8.6.0+14118+d530a951.src
    - compiler-rt-0:13.0.1-1.module+el8.6.0+14118+d530a951.x86_64
    - llvm-0:13.0.1-1.module+el8.6.0+14118+d530a951.i686
    - llvm-0:13.0.1-1.module+el8.6.0+14118+d530a951.src
    - llvm-0:13.0.1-1.module+el8.6.0+14118+d530a951.x86_64
    - python-lit-0:13.0.1-1.module+el8.6.0+14118+d530a951.src
    - python3-lit-0:13.0.1-1.module+el8.6.0+14118+d530a951.noarch
...
---
document: modulemd
version: 2
data:
  name: llvm-toolset-devel
  stream: "rhel8"
  version: 8060020220204053142
  context: d63f516d
  arch: x86_64
  summary: LLVM
  description: >-
    LLVM Tools and libraries
  license:
    module:
    - MIT
    content:
    - NCSA
    - NCSA and MIT
    - NCSA or MIT
  xmd: {}
  dependencies:
  - buildrequires:
      platform: [el8.6.0]
    requires:
      platform: [el8]
  profiles:
    common:
      rpms:
      - llvm-toolset
  api:
    rpms:
    - clang
    - clang-analyzer
    - clang-devel
    - clang-libs
    - clang-tools-extra
    - git-clang-format
    - lld
    - lld-libs
    - lldb
    - lldb-devel
    - llvm
    - llvm-devel
    - llvm-libs
  components:
    rpms:
      clang:
        rationale: clang tools and libraries
        ref: stream-rhel-8-rhel-8.6.0
        buildorder: 1
        arches: [aarch64, i686, ppc64le, s390x, x86_64]
        multilib: [x86_64]
      compiler-rt:
        rationale: LLVM compiler intrinsic and sanitizer libraries
        ref: stream-rhel-8-rhel-8.6.0
        buildorder: 1
        arches: [aarch64, i686, ppc64le, s390x, x86_64]
        multilib: [x86_64]
      libomp:
        rationale: LLVM OpenMP runtime
        ref: stream-rhel-8-rhel-8.6.0
        buildorder: 2
        arches: [aarch64, i686, ppc64le, s390x, x86_64]
        multilib: [x86_64]
      lld:
        rationale: LLVM linker
        ref: stream-rhel-8-rhel-8.6.0
        buildorder: 1
        arches: [aarch64, i686, ppc64le, s390x, x86_64]
        multilib: [x86_64]
      lldb:
        rationale: lldb debugger
        ref: stream-rhel-8-rhel-8.6.0
        buildorder: 2
        arches: [aarch64, i686, ppc64le, s390x, x86_64]
        multilib: [x86_64]
      llvm:
        rationale: LLVM tools and libraries
        ref: stream-rhel-8-rhel-8.6.0
        arches: [aarch64, i686, ppc64le, s390x, x86_64]
        multilib: [x86_64]
      python-lit:
        rationale: Lit test runner for LLVM
        ref: stream-rhel-8-rhel-8.6.0
        arches: [aarch64, i686, ppc64le, s390x, x86_64]
...
"""


@pytest.fixture
def modules_artifacts():
    return {
        "virt:ppc64le": [
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
        "virt-devel:ppc64le": [
            "ocaml-hivex-0:1.3.18-23.module_el8.6.0+2880+7d9e3703.ppc64le",
            "ocaml-hivex-debuginfo-0:1.3.18-23.module_el8.6.0+2880+7d9e3703.ppc64le",
            "ocaml-hivex-devel-0:1.3.18-23.module_el8.6.0+2880+7d9e3703.ppc64le",
        ],
        "virt:i686": [
            "hivex-0:1.3.18-23.module_el8.6.0+2880+7d9e3703.i686",
            "hivex-0:1.3.18-23.module_el8.6.0+2880+7d9e3703.src",
            "hivex-debuginfo-0:1.3.18-23.module_el8.6.0+2880+7d9e3703.i686",
            "hivex-debugsource-0:1.3.18-23.module_el8.6.0+2880+7d9e3703.i686",
            "hivex-devel-0:1.3.18-23.module_el8.6.0+2880+7d9e3703.i686",
        ],
        "virt-devel:i686": [
            "SLOF-0:20210217-1.module_el8.6.0+2880+7d9e3703.src",
            "ocaml-hivex-0:1.3.18-23.module_el8.6.0+2880+7d9e3703.i686",
            "ocaml-hivex-debuginfo-0:1.3.18-23.module_el8.6.0+2880+7d9e3703.i686",
            "ocaml-hivex-devel-0:1.3.18-23.module_el8.6.0+2880+7d9e3703.i686",
            "qemu-kvm-0:6.2.0-32.module_el8.8.0+3553+bd08596b.src",
        ],
        "ruby:aarch64": [
            "ruby-0:3.1.2-141.module_el8.1.0+8+503f6fbd.aarch64",
            "ruby-0:3.1.2-141.module_el8.1.0+8+503f6fbd.src",
            "ruby-debuginfo-0:3.1.2-141.module_el8.1.0+8+503f6fbd.aarch64",
            "ruby-debugsource-0:3.1.2-141.module_el8.1.0+8+503f6fbd.aarch64",
            "ruby-devel-0:3.1.2-141.module_el8.1.0+8+503f6fbd.aarch64",
            "rubygem-pg-0:1.3.5-1.module_el8.1.0+8+503f6fbd.src",
            "rubygem-pg-1.3.5-0:1-141.module_el8.1.0+8+503f6fbd.aarch64",
            "rubygem-pg-debuginfo-0:3.1.2-141.module_el8.1.0+8+503f6fbd.aarch64",
            "rubygem-pg-debugsource-0:3.1.2-141.module_el8.1.0+8+503f6fbd.aarch64",
            "rubygem-pg-doc-0:3.3.7-141.module_el8.1.0+8+503f6fbd.noarch",
            "rubygems-0:3.3.7-141.module_el8.1.0+8+503f6fbd.noarch",
            "rubygems-devel-0:3.3.7-141.module_el8.1.0+8+503f6fbd.noarch",
        ],
        "ruby-devel:aarch64": [],
        "ruby:i686": [
            "ruby-0:3.1.2-141.module_el8.1.0+8+503f6fbd.i686",
            "ruby-0:3.1.2-141.module_el8.1.0+8+503f6fbd.src",
            "ruby-debuginfo-0:3.1.2-141.module_el8.1.0+8+503f6fbd.i686",
            "ruby-debugsource-0:3.1.2-141.module_el8.1.0+8+503f6fbd.i686",
            "ruby-devel-0:3.1.2-141.module_el8.1.0+8+503f6fbd.i686",
            "rubygem-pg-0:1.3.5-1.module_el8.1.0+8+503f6fbd.src",
            "rubygem-pg-1.3.5-0:1-141.module_el8.1.0+8+503f6fbd.i686",
            "rubygem-pg-debuginfo-0:3.1.2-141.module_el8.1.0+8+503f6fbd.i686",
            "rubygem-pg-debugsource-0:3.1.2-141.module_el8.1.0+8+503f6fbd.i686",
            "rubygem-pg-doc-0:3.3.7-141.module_el8.1.0+8+503f6fbd.noarch",
            "rubygems-0:3.3.7-141.module_el8.1.0+8+503f6fbd.noarch",
            "rubygems-devel-0:3.3.7-141.module_el8.1.0+8+503f6fbd.noarch",
        ],
        "ruby-devel:i686": [],
        "subversion:aarch64": [
            "subversion-0:1.10.2-5.module_el8.6.0+3347+66c1e1d6.aarch64",
            "subversion-0:1.10.2-5.module_el8.6.0+3347+66c1e1d6.src",
            "subversion-debuginfo-0:1.10.2-5.module_el8.6.0+3347+66c1e1d6.aarch64",
            "subversion-debugsource-0:1.10.2-5.module_el8.6.0+3347+66c1e1d6.aarch64",
            "subversion-devel-0:1.10.2-5.module_el8.6.0+3347+66c1e1d6.aarch64",
        ],
        "subversion-devel:aarch64": [
            "subversion-ruby-0:1.10.2-5.module_el8.6.0+3347+66c1e1d6.aarch64",
        ],
        "subversion:i686": [
            "subversion-0:1.10.2-5.module_el8.6.0+3347+66c1e1d6.i686",
            "subversion-0:1.10.2-5.module_el8.6.0+3347+66c1e1d6.src",
            "subversion-debuginfo-0:1.10.2-5.module_el8.6.0+3347+66c1e1d6.i686",
            "subversion-debugsource-0:1.10.2-5.module_el8.6.0+3347+66c1e1d6.i686",
            "subversion-devel-0:1.10.2-5.module_el8.6.0+3347+66c1e1d6.i686",
        ],
        "subversion-devel:i686": [
            "subversion-ruby-0:1.10.2-5.module_el8.6.0+3347+66c1e1d6.i686",
        ],
        "llvm-toolset:i686": [
            "clang-0:13.0.1-1.module+el8.6.0+14118+d530a951.i686",
            "clang-0:13.0.1-1.module+el8.6.0+14118+d530a951.src",
            "compiler-rt-0:13.0.1-1.module+el8.6.0+14118+d530a951.i686",
            "compiler-rt-0:13.0.1-1.module+el8.6.0+14118+d530a951.src",
            "llvm-0:13.0.1-1.module+el8.6.0+14118+d530a951.i686",
            "llvm-0:13.0.1-1.module+el8.6.0+14118+d530a951.src",
            "python-lit-0:13.0.1-1.module+el8.6.0+14118+d530a951.src",
            "python3-lit-0:13.0.1-1.module+el8.6.0+14118+d530a951.noarch",
        ],
        "llvm-toolset-devel:i686": [],
    }

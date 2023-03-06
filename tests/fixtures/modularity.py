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

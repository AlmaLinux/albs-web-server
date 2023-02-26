import pytest

from alws import models


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
async def create_rpm_module(async_session):
    module = models.RpmModule(
        name="go-toolset-devel",
        stream="rhel8",
        version="8070020230125092346",
        context="b754926a",
        arch="i686",
        pulp_href="test",
        sha256="aabbccddeeff"
    )
    async_session.add(module)
    await async_session.commit()

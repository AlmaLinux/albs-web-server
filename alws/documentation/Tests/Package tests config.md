## Package tests config

ALTS tests every binary package that ALBS builds, one test task per package
and architecture. A task goes through these stages:

| Stage | What it does | Configurable |
|-------|--------------|--------------|
| `initialize_terraform`, `start_environment`, `initial_provision` | prepare a clean container of the target platform | no |
| `system_info` | collect information about the environment | no |
| `install_package` | install the package | yes |
| `package_integrity_tests` | check files, dependencies and RPATHs of the package (only when integrity tests are enabled in ALTS) | yes |
| `third_party_tests` | run the third-party tests set up for the build, each test file is reported as `third_party_test_<file>` | yes |
| `uninstall_package` | remove the package | yes |
| `stop_environment` | remove the container | no |

Some packages fail these tests by design. For example,
`systemd-standalone-tmpfiles` and `systemd-standalone-sysusers` conflict with
`systemd`, which the test container always has, so they can never be
installed there. A package tests config tells ALBS which tests not to run for
a package and which failures to expect.

### Where the config lives

The config of a package is `alts.yaml` in the root of the `main` branch of
`https://git.almalinux.org/tests/<package>`, where `<package>` is the name of
the package repository in `https://git.almalinux.org/rpms`. For example, the
config of systemd is
`https://git.almalinux.org/tests/systemd/src/branch/main/alts.yaml`. The name
comes from the git URL of the build; for a build from an SRPM it's the name
of the source package with `+` spelled as `plus`, e.g. `libsigcplusplus20`.

There is nothing to register in ALBS: it looks the config up by itself.
Changes are picked up within 5 minutes (lookups are cached). Packages
without a tests repository or without `alts.yaml` are tested as before.

The organization, branch, file name and cache lifetime are set with the
`PACKAGE_TESTS_ORG`, `PACKAGE_TESTS_BRANCH`, `PACKAGE_TESTS_CONFIG_PATH` and
`PACKAGE_TESTS_CACHE_TTL` settings; `PACKAGE_TESTS_ENABLED=false` turns the
lookups off.

### Format

```yaml
version: 1

# Tests that aren't run
skip:
  # No "tests": these packages aren't tested at all
  - packages: ['*-debuginfo', '*-debugsource']
    reason: Debug information, nothing to test
  - tests: [uninstall_package]
    packages: [foo-core]
    reason: Removing foo-core breaks the test container

# Tests that run, but their failures don't fail the test task
expected_failures:
  - tests: [install_package]
    packages:
      - systemd-standalone-sysusers
      - systemd-standalone-tmpfiles
    reason: >-
      The standalone sysusers/tmpfiles builds conflict with systemd, which
      the test container always has installed.
```

A `skip` rule with neither `tests` nor `packages` switches the tests off for
the whole source package:

```yaml
skip:
  - reason: Can't be tested in a container
```

Both `skip` and `expected_failures` are lists of rules with these fields:

| Field | Required | Meaning |
|-------|----------|---------|
| `tests` | yes for `expected_failures`; in `skip`, no field means that the package isn't tested at all | `install_package`, `package_integrity_tests`, `third_party_tests`, `uninstall_package`, or a single third-party test as `third_party_test_<file>` (a pattern is allowed: `third_party_test_*.bats`) |
| `reason` | yes | why, keep a link to the build or the issue here |
| `packages` | no | binary packages the rule applies to; all packages built from the source package by default |
| `platforms` | no | ALBS platforms the rule applies to, e.g. `AlmaLinux-9`, `AlmaLinux-Kitten-10`; all platforms by default |
| `arches` | no | architectures the rule applies to, e.g. `x86_64`, `aarch64`; all architectures by default |

`packages`, `platforms` and `arches` take shell-style patterns (`*`, `?`,
`[...]`), matched case-insensitively. Quote a pattern that starts with `*`,
otherwise YAML reads it as an alias: `packages: ['*-debuginfo']`. The list
fields also accept a single value instead of a list.

The config is validated strictly: an unknown key, an unknown test name or a
rule without `reason` makes ALBS ignore the whole config, so the failures stay
failures until the config is fixed.

### What it changes

- **Packages skipped completely** (a `skip` rule without `tests`) get no test
  task, so ALTS doesn't test them at all.
- **Skipped tests** are sent to ALTS as `skipped_tests` of the test task and
  are also stored with it. Until ALTS supports this, it still runs them, but
  their results never fail the test task.
- **Expected failures** don't fail the test task. A failed third-party test
  also fails `third_party_tests_wrapper`, which is then judged by that test.
  Failures of the test environment can't be skipped or expected.

The ALTS result itself isn't changed: an expected failure still shows up as a
failed stage in the test logs. What the config did is stored next to it in the
`tests_config` field of the test task's `alts_response`
(`GET /api/v1/tests/<build_task_id>/latest`):

```json
{
  "url": "https://git.almalinux.org/tests/systemd/src/branch/main/alts.yaml",
  "commit": "<last commit of alts.yaml>",
  "skipped": [{"test": "uninstall_package", "reason": "dnf refuses ..."}],
  "expected_failures": [
    {"test": "install_package", "reason": "The standalone sysusers/tmpfiles ..."}
  ],
  "unexpected_passes": ["install_package"],
  "error": "Invalid config: ..."
}
```

`unexpected_passes` lists the tests that a rule expects to fail but that have
passed; such a rule may be obsolete. `error` explains why the config couldn't
be used. The field is absent when the package has no config.

A config applies to the test tasks created after it and to the test results
that come after it. To re-check a build that has already been tested,
restart its tests. Restarting only the failed tests re-tests just the packages
that haven't passed, the others keep their results in the new revision.

import time

import aiohttp
import pytest
import yaml
from pydantic import ValidationError

from alws.schemas.package_tests_schema import MatchedRules, PackageTestsConfig
from alws.utils import package_tests
from alws.utils.package_tests import (
    PackageTestsConfigLookup,
    collect_checks,
    evaluate_test_result,
    get_matched_rules,
    get_package_tests_config,
    get_source_package_name,
    selects,
)
from tests.fixtures.tests import (
    PackageTestsConfigs,
    install_failed_result,
    passed_result,
)

pytestmark = pytest.mark.anyio

SYSTEMD_CONFIG_YAML = """
version: 1
expected_failures:
  - tests: [install_package]
    packages: [systemd-standalone-*]
    reason: Conflicts with systemd from the test image
"""
SYSTEMD_CONFIG = yaml.safe_load(SYSTEMD_CONFIG_YAML)


def third_party_result(**tests: bool) -> dict:
    """Result where third-party test files ran with the given outcomes."""
    return {
        **passed_result(),
        'third_party_tests_wrapper': {'success': all(tests.values())},
        'third_party': {
            f'third_party_test_{name}': {'success': success}
            for name, success in tests.items()
        },
    }


def rules(config: dict) -> MatchedRules:
    """All rules of the config, as if they matched the test task."""
    parsed = PackageTestsConfig.model_validate(config)
    return MatchedRules(
        skip=parsed.skip,
        expected_failures=parsed.expected_failures,
    )


class TestPackageTestsConfig:
    async def test_systemd_config(self):
        config = PackageTestsConfig.model_validate(SYSTEMD_CONFIG)
        rule = config.expected_failures[0]
        assert rule.tests == ['install_package']
        assert rule.platforms is None
        assert rule.arches is None
        assert config.skip == []

    async def test_empty_config(self):
        config = PackageTestsConfig.model_validate({})
        assert config.version == 1
        assert config.get_rules('foo', 'AlmaLinux-9', 'x86_64') == (
            MatchedRules()
        )

    async def test_skip_whole_package(self):
        config = PackageTestsConfig.model_validate(
            {'skip': [{'reason': 'Cannot be tested in a container'}]}
        )
        rule = config.skip[0]
        assert rule.tests is None
        assert rule.packages is None

    async def test_single_values_become_lists(self):
        rule = {
            'tests': 'uninstall_package',
            'packages': 'foo',
            'platforms': 'AlmaLinux-10',
            'arches': 'x86_64_v2',
            'reason': 'Protected package',
        }
        config = PackageTestsConfig.model_validate(
            {'skip': [rule], 'expected_failures': [rule]}
        )
        for parsed in (config.skip[0], config.expected_failures[0]):
            assert parsed.tests == ['uninstall_package']
            assert parsed.packages == ['foo']
            assert parsed.platforms == ['AlmaLinux-10']
            assert parsed.arches == ['x86_64_v2']

    @pytest.mark.parametrize(
        'test',
        [
            'install_package',
            'package_integrity_tests',
            'third_party_tests',
            'third_party_test_smoke.sh',
            'third_party_test_*.bats',
            'uninstall_package',
        ],
    )
    async def test_valid_test_name(self, test: str):
        PackageTestsConfig.model_validate({
            'skip': [{'tests': [test], 'reason': 'x'}],
            'expected_failures': [{'tests': [test], 'reason': 'x'}],
        })

    @pytest.mark.parametrize(
        'rule',
        [
            pytest.param(
                {'tests': ['install_pkg'], 'reason': 'typo'},
                id='unknown-test',
            ),
            pytest.param(
                {'tests': ['initial_provision'], 'reason': 'environment'},
                id='environment-stage',
            ),
            pytest.param(
                {'tests': ['system_info'], 'reason': 'environment'},
                id='system-info',
            ),
            pytest.param(
                {'tests': ['third_party_test_'], 'reason': 'no file'},
                id='third-party-test-without-file',
            ),
            pytest.param({'tests': [], 'reason': 'nothing'}, id='no-tests'),
            pytest.param({'tests': ['install_package']}, id='no-reason'),
            pytest.param(
                {'tests': ['install_package'], 'reason': '  '},
                id='blank-reason',
            ),
            pytest.param(
                {'tests': ['install_package'], 'packages': [], 'reason': 'x'},
                id='empty-filter',
            ),
            pytest.param(
                {'tests': ['install_package'], 'package': 'foo', 'reason': 'x'},
                id='misspelled-key',
            ),
        ],
    )
    @pytest.mark.parametrize('section', ['skip', 'expected_failures'])
    async def test_invalid_rule(self, section: str, rule: dict):
        with pytest.raises(ValidationError):
            PackageTestsConfig.model_validate({section: [rule]})

    async def test_expected_failure_without_tests(self):
        with pytest.raises(ValidationError):
            PackageTestsConfig.model_validate(
                {'expected_failures': [{'reason': 'Everything fails'}]}
            )

    @pytest.mark.parametrize(
        'config',
        [
            pytest.param({'version': 2}, id='unsupported-version'),
            pytest.param({'skipped': []}, id='misspelled-section'),
            pytest.param({'common_tests': {}}, id='unknown-section'),
        ],
    )
    async def test_invalid_config(self, config: dict):
        with pytest.raises(ValidationError):
            PackageTestsConfig.model_validate(config)

    @pytest.mark.parametrize(
        'package, platform, arch, matches',
        [
            ('systemd-standalone-tmpfiles', 'AlmaLinux-9', 'x86_64', True),
            ('systemd-standalone-sysusers', 'AlmaLinux-9', 'aarch64', False),
            ('systemd-standalone-sysusers', 'AlmaLinux-10', 'ppc64le', True),
            ('systemd-standalone-tmpfiles', 'almalinux-10', 'PPC64LE', True),
            ('systemd-standalone-tmpfiles', 'AlmaLinux-8', 'x86_64', False),
            ('systemd', 'AlmaLinux-9', 'x86_64', False),
        ],
    )
    async def test_rule_filters(
        self,
        package: str,
        platform: str,
        arch: str,
        matches: bool,
    ):
        rule = {
            'tests': ['install_package'],
            'packages': ['systemd-standalone-*'],
            'platforms': ['AlmaLinux-9', 'AlmaLinux-1?'],
            'arches': ['x86_64', 'ppc64le'],
            'reason': 'Conflicts with systemd',
        }
        config = PackageTestsConfig.model_validate(
            {'skip': [rule], 'expected_failures': [rule]}
        )
        matched = config.get_rules(package, platform, arch)
        assert bool(matched.skip) is matches
        assert bool(matched.expected_failures) is matches


class TestMatchedRules:
    async def test_skipped_tests(self):
        matched = rules({
            'skip': [
                {'tests': ['uninstall_package'], 'reason': 'Protected'},
                {
                    'tests': ['third_party_tests', 'uninstall_package'],
                    'reason': 'Broken',
                },
            ],
        })
        assert matched.skipped_package is None
        assert matched.skipped_tests == [
            'uninstall_package',
            'third_party_tests',
        ]

    async def test_skipped_package(self):
        matched = rules({
            'skip': [
                {'tests': ['uninstall_package'], 'reason': 'Protected'},
                {'packages': ['*-debuginfo'], 'reason': 'Nothing to test'},
            ],
        })
        assert matched.skipped_package.reason == 'Nothing to test'

    async def test_no_config(self):
        assert get_matched_rules(None, 'foo', 'AlmaLinux-9', 'x86_64') == (
            MatchedRules()
        )


@pytest.mark.parametrize(
    'url, name',
    [
        ('https://git.almalinux.org/rpms/systemd.git', 'systemd'),
        ('https://git.almalinux.org/rpms/systemd', 'systemd'),
        ('https://git.almalinux.org/rpms/systemd/', 'systemd'),
        ('https://git.almalinux.org/rpms/libsigc--20.git', 'libsigc--20'),
        ('https://github.com/AlmaLinux/leapp.git', 'leapp'),
        (
            'https://build.almalinux.org/pulp/content/'
            'systemd-252-67.el9.src.rpm',
            'systemd',
        ),
        (
            'https://example.com/libsigc++20-2.10.7-6.el9.src.rpm',
            'libsigcplusplus20',
        ),
        ('https://example.com/garbage.src.rpm', None),
        ('https://example.com/..-1-1.src.rpm', None),
        ('https://example.com/rpms/..', None),
        ('https://example.com/', None),
    ],
)
async def test_get_source_package_name(url: str, name: str):
    assert get_source_package_name(url) == name


async def test_collect_checks():
    result = {
        **passed_result(),
        'revoked': False,
        'tests': {'package_integrity_tests': {'success': False}},
        'third_party': {
            'third_party_test_smoke.sh': {'success': True},
            'third_party_test_broken.sh': {'success': False},
        },
        'Unexpected errors during tests': {},
    }
    checks = collect_checks(result)
    assert 'logs' not in checks
    assert 'skipped_tests' not in checks
    assert 'revoked' not in checks
    assert 'tests' not in checks
    assert 'third_party' not in checks
    assert checks['install_package'] is True
    assert checks['package_integrity_tests'] is False
    assert checks['third_party_test_smoke.sh'] is True
    assert checks['third_party_test_broken.sh'] is False
    assert checks['Unexpected errors during tests'] is False


@pytest.mark.parametrize(
    'test, check, covered',
    [
        ('install_package', 'install_package', True),
        ('install_package', 'uninstall_package', False),
        ('package_integrity_tests', 'package_integrity_tests', True),
        ('third_party_tests', 'third_party_tests_wrapper', True),
        ('third_party_tests', 'third_party_test_smoke.sh', True),
        ('third_party_tests', 'install_package', False),
        ('third_party_test_smoke.sh', 'third_party_test_smoke.sh', True),
        ('third_party_test_smoke.sh', 'third_party_test_other.sh', False),
        ('third_party_test_smoke.sh', 'third_party_tests_wrapper', False),
        ('third_party_test_*.bats', 'third_party_test_x.bats', True),
        ('third_party_test_*.bats', 'third_party_test_x.sh', False),
        ('third_party_test_*', 'third_party_tests_wrapper', False),
    ],
)
async def test_selects(test: str, check: str, covered: bool):
    assert selects(test, check) is covered


class TestEvaluateTestResult:
    systemd_rules = rules(SYSTEMD_CONFIG)

    async def test_passed(self):
        verdict = evaluate_test_result(passed_result())
        assert not verdict.failed
        assert verdict.skipped == []
        assert verdict.expected_failures == []
        assert verdict.unexpected_passes == []

    async def test_failed_without_rules(self):
        verdict = evaluate_test_result(install_failed_result())
        assert verdict.failed
        assert verdict.expected_failures == []

    async def test_expected_failure(self):
        verdict = evaluate_test_result(
            install_failed_result(),
            self.systemd_rules,
        )
        assert not verdict.failed
        assert verdict.expected_failures == [{
            'test': 'install_package',
            'reason': 'Conflicts with systemd from the test image',
        }]
        assert verdict.unexpected_passes == []

    async def test_unexpected_failure_next_to_expected_one(self):
        result = {
            **install_failed_result(),
            'stop_environment': {'success': False},
        }
        verdict = evaluate_test_result(result, self.systemd_rules)
        assert verdict.failed
        assert [i['test'] for i in verdict.expected_failures] == [
            'install_package'
        ]

    async def test_environment_failure_is_never_covered(self):
        result = {
            **install_failed_result(),
            'initial_provision': {'success': False},
        }
        result.pop('install_package')
        assert evaluate_test_result(result, self.systemd_rules).failed

    async def test_unexpected_pass(self):
        verdict = evaluate_test_result(passed_result(), self.systemd_rules)
        assert not verdict.failed
        assert verdict.expected_failures == []
        assert verdict.unexpected_passes == ['install_package']

    async def test_integrity_tests(self):
        result = {
            **passed_result(),
            'tests': {'package_integrity_tests': {'success': False}},
        }
        assert evaluate_test_result(result).failed
        for section in ('skip', 'expected_failures'):
            config = {
                section: [{
                    'tests': ['package_integrity_tests'],
                    'reason': 'Bundled libraries',
                }]
            }
            assert not evaluate_test_result(result, rules(config)).failed

    async def test_skipped_test(self):
        result = {
            **passed_result(),
            'uninstall_package': {'success': False},
        }
        config = {
            'skip': [{'tests': ['uninstall_package'], 'reason': 'Protected'}],
            'expected_failures': [
                {'tests': ['uninstall_package'], 'reason': 'Expected'}
            ],
        }
        verdict = evaluate_test_result(result, rules(config))
        assert not verdict.failed
        assert verdict.skipped == [
            {'test': 'uninstall_package', 'reason': 'Protected'}
        ]
        # The result of a skipped test means nothing either way
        assert verdict.expected_failures == []
        assert verdict.unexpected_passes == []

    async def test_skipped_package(self):
        result = {
            **install_failed_result(),
            'initial_provision': {'success': False},
        }
        verdict = evaluate_test_result(
            result,
            rules({
                'skip': [
                    {'tests': ['uninstall_package'], 'reason': 'Protected'},
                    {'reason': 'Not testable'},
                ],
            }),
        )
        assert not verdict.failed
        assert verdict.skipped == [
            {'test': 'uninstall_package', 'reason': 'Protected'},
            {'test': 'all', 'reason': 'Not testable'},
        ]

    async def test_failed_third_party_test(self):
        result = third_party_result(**{'smoke.sh': False, 'other.sh': True})
        assert evaluate_test_result(result).failed

    async def test_passed_third_party_test(self):
        assert not evaluate_test_result(
            third_party_result(**{'smoke.sh': True})
        ).failed

    @pytest.mark.parametrize('section', ['skip', 'expected_failures'])
    @pytest.mark.parametrize(
        'test',
        [
            'third_party_test_smoke.sh',
            'third_party_test_s*',
            'third_party_tests',
        ],
    )
    async def test_covered_third_party_test(self, section: str, test: str):
        result = third_party_result(**{'smoke.sh': False, 'other.sh': True})
        config = {section: [{'tests': [test], 'reason': 'Flaky'}]}
        verdict = evaluate_test_result(result, rules(config))
        assert not verdict.failed

    async def test_other_third_party_test_fails(self):
        result = third_party_result(**{'smoke.sh': False, 'other.sh': False})
        config = {
            'expected_failures': [
                {'tests': ['third_party_test_smoke.sh'], 'reason': 'Flaky'}
            ],
        }
        verdict = evaluate_test_result(result, rules(config))
        assert verdict.failed
        assert verdict.expected_failures == [
            {'test': 'third_party_test_smoke.sh', 'reason': 'Flaky'}
        ]

    async def test_third_party_tests_not_run(self):
        # E.g. the tests repository couldn't be cloned
        result = {
            **passed_result(),
            'third_party_tests_wrapper': {'success': False},
        }
        assert evaluate_test_result(result).failed
        config = {
            'expected_failures': [
                {'tests': ['third_party_test_smoke.sh'], 'reason': 'Flaky'}
            ],
        }
        assert evaluate_test_result(result, rules(config)).failed
        config = {
            'expected_failures': [
                {'tests': ['third_party_tests'], 'reason': 'Broken tests'}
            ],
        }
        assert not evaluate_test_result(result, rules(config)).failed


class TestGetPackageTestsConfig:
    async def test_no_config(self):
        lookup = await get_package_tests_config('systemd')
        assert lookup == PackageTestsConfigLookup()
        assert lookup.to_dict() is None

    async def test_valid_config(
        self,
        package_tests_configs: PackageTestsConfigs,
    ):
        package_tests_configs['systemd'] = SYSTEMD_CONFIG_YAML
        lookup = await get_package_tests_config('systemd')
        assert lookup.error is None
        assert lookup.config == PackageTestsConfig.model_validate(
            SYSTEMD_CONFIG
        )
        assert lookup.to_dict() == {
            'url': (
                'https://git.almalinux.org/tests/systemd'
                '/src/branch/main/alts.yaml'
            ),
            'commit': 'c0ffee',
        }

    async def test_empty_file(self, package_tests_configs: PackageTestsConfigs):
        package_tests_configs['systemd'] = ''
        lookup = await get_package_tests_config('systemd')
        assert lookup.error is None
        assert lookup.config == PackageTestsConfig()

    @pytest.mark.parametrize(
        'content',
        [
            pytest.param('expected_failures: [', id='broken-yaml'),
            pytest.param('- install_package', id='not-a-mapping'),
            pytest.param(
                SYSTEMD_CONFIG_YAML.replace('reason', 'reasons'),
                id='misspelled-key',
            ),
        ],
    )
    async def test_invalid_config(
        self,
        package_tests_configs: PackageTestsConfigs,
        content: str,
    ):
        package_tests_configs['systemd'] = content
        lookup = await get_package_tests_config('systemd')
        assert lookup.config is None
        assert lookup.error.startswith('Invalid config')
        assert lookup.to_dict()['error'] == lookup.error

    async def test_directory_instead_of_file(
        self,
        package_tests_configs: PackageTestsConfigs,
    ):
        package_tests_configs['systemd'] = [
            {'type': 'file', 'name': 'main.fmf'}
        ]
        lookup = await get_package_tests_config('systemd')
        assert lookup.config is None
        assert lookup.error.endswith('is not a file')

    async def test_lookups_are_cached(
        self,
        package_tests_configs: PackageTestsConfigs,
    ):
        package_tests_configs['systemd'] = '{}'
        await get_package_tests_config('systemd')
        await get_package_tests_config('systemd')
        await get_package_tests_config('bash')
        assert package_tests_configs.lookups == ['systemd', 'bash']

    async def test_fetch_error(
        self, package_tests_configs: PackageTestsConfigs
    ):
        package_tests_configs['systemd'] = aiohttp.ClientConnectionError(
            'Connection refused'
        )
        lookup = await get_package_tests_config('systemd')
        assert lookup.config is None
        assert lookup.error == (
            'Cannot fetch the config: ClientConnectionError: Connection refused'
        )
        assert lookup.url == (
            'https://git.almalinux.org/tests/systemd/src/branch/main/alts.yaml'
        )
        # Gitea isn't asked again right away, but sooner than usual
        await get_package_tests_config('systemd')
        expires_at, _ = package_tests._lookups_cache['systemd']
        assert package_tests_configs.lookups == ['systemd']
        assert (
            expires_at - time.monotonic()
            <= package_tests.FAILED_FETCH_CACHE_TTL
        )

    async def test_disabled(
        self,
        monkeypatch,
        package_tests_configs: PackageTestsConfigs,
    ):
        package_tests_configs['systemd'] = 'version: 2'
        monkeypatch.setattr(
            package_tests.settings,
            'package_tests_enabled',
            False,
        )
        assert (
            await get_package_tests_config('systemd')
            == PackageTestsConfigLookup()
        )
        assert package_tests_configs.lookups == []

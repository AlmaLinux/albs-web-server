"""Per-package tests config from git and its effect on ALTS results.

The config of a package lives in the repository of the tests organization
named like the package repository in git.almalinux.org/rpms, e.g.
git.almalinux.org/tests/systemd for git.almalinux.org/rpms/systemd.
"""

import base64
import dataclasses
import fnmatch
import logging
import time
import typing
import urllib.parse

import aiohttp
import hawkey
import yaml

from alws.config import settings
from alws.schemas.package_tests_schema import (
    THIRD_PARTY_TEST_PREFIX,
    ExpectedFailureRule,
    MatchedRules,
    PackageTestsConfig,
    SkipRule,
)
from alws.utils.parsing import parse_rpm_nevra

__all__ = [
    'PackageTestsConfigLookup',
    'ResultVerdict',
    'collect_checks',
    'evaluate_test_result',
    'get_matched_rules',
    'get_package_tests_config',
    'get_source_package_name',
    'selects',
]


# Test results wait for the lookup, a stuck Gitea shouldn't hold them long
FETCH_TIMEOUT = 10  # seconds
# Lookups that couldn't reach Gitea are retried sooner than the cache expires
FAILED_FETCH_CACHE_TTL = 60  # seconds
# ALTS reports these sections as {check: {'success': ...}} instead of being
# a single {'success': ...} check
NESTED_RESULT_SECTIONS = ('tests', 'third_party')
SERVICE_RESULT_KEYS = ('logs', 'skipped_tests', 'revoked')
# Fails whenever any third-party test fails, or the tests couldn't be run
THIRD_PARTY_WRAPPER = 'third_party_tests_wrapper'
# Stands for all tests of a package in the reports
ALL_TESTS = 'all'


@dataclasses.dataclass(frozen=True)
class PackageTestsConfigLookup:
    """Outcome of looking a package tests config up in git.

    ``url`` is None when the package has no config at all, ``error`` is set
    when the config exists but couldn't be fetched or is invalid.
    """

    url: typing.Optional[str] = None
    commit: typing.Optional[str] = None
    config: typing.Optional[PackageTestsConfig] = None
    error: typing.Optional[str] = None

    def to_dict(self) -> typing.Optional[dict]:
        if not self.url:
            return None
        info = {'url': self.url, 'commit': self.commit}
        if self.error:
            info['error'] = self.error
        return info


@dataclasses.dataclass(frozen=True)
class ResultVerdict:
    failed: bool
    # [{'test': <test from the config>, 'reason': <rule reason>}] for the
    # tests the config doesn't run for the package, the results of those
    # that ran anyway are ignored
    skipped: typing.List[dict]
    # [{'test': <check>, 'reason': <rule reason>}] for the checks that
    # failed as the config expects
    expected_failures: typing.List[dict]
    # Checks expected to fail which have passed, their rules may be obsolete
    unexpected_passes: typing.List[str]


def get_source_package_name(ref_url: str) -> typing.Optional[str]:
    """Name of the package repository in git.almalinux.org/rpms."""
    name = urllib.parse.urlparse(ref_url).path.rstrip('/').split('/')[-1]
    if name.endswith('.src.rpm'):
        try:
            # The newer rpms repositories spell "+" so, e.g. libsigcplusplus20
            name = parse_rpm_nevra(name).name.replace('+', 'plus')
        except hawkey.ValueException:
            return None
    else:
        name = name.removesuffix('.git')
    # Not names of repositories, but would change the path of the request
    if name in ('', '.', '..'):
        return None
    return name


_lookups_cache: typing.Dict[
    str,
    typing.Tuple[float, PackageTestsConfigLookup],
] = {}


def _get_web_url(package_name: str) -> str:
    return urllib.parse.urljoin(
        settings.gitea_host,
        f'/{settings.package_tests_org}/{package_name}/src/branch/'
        f'{settings.package_tests_branch}/'
        f'{settings.package_tests_config_path}',
    )


async def _fetch_config_file(package_name: str) -> typing.Any:
    """Gitea contents entry of the config, None if there is no such file."""
    endpoint = '/'.join((
        'repos',
        urllib.parse.quote(settings.package_tests_org, safe=''),
        urllib.parse.quote(package_name, safe=''),
        'contents',
        urllib.parse.quote(settings.package_tests_config_path),
    ))
    async with aiohttp.ClientSession(
        trust_env=True,
        timeout=aiohttp.ClientTimeout(total=FETCH_TIMEOUT),
    ) as session:
        async with session.get(
            urllib.parse.urljoin(settings.gitea_host, endpoint),
            params={'ref': settings.package_tests_branch},
        ) as response:
            # Gitea answers 404 for a missing repository and file alike
            if response.status == 404:
                return None
            response.raise_for_status()
            return await response.json()


async def _load_config(package_name: str) -> PackageTestsConfigLookup:
    file_info = await _fetch_config_file(package_name)
    if file_info is None:
        return PackageTestsConfigLookup()
    if not isinstance(file_info, dict) or file_info.get('type') != 'file':
        url = _get_web_url(package_name)
        return PackageTestsConfigLookup(url=url, error=f'{url} is not a file')
    url = file_info.get('html_url') or _get_web_url(package_name)
    commit = file_info.get('last_commit_sha')
    try:
        content = base64.b64decode(file_info['content']).decode('utf-8')
        config = PackageTestsConfig.model_validate(
            yaml.safe_load(content) or {}
        )
    # ValidationError of pydantic is a ValueError too
    except (KeyError, TypeError, ValueError, yaml.YAMLError) as exc:
        logging.warning('Tests config %s is invalid: %s', url, exc)
        return PackageTestsConfigLookup(
            url=url,
            commit=commit,
            error=f'Invalid config: {exc}',
        )
    return PackageTestsConfigLookup(url=url, commit=commit, config=config)


async def get_package_tests_config(
    package_name: str,
) -> PackageTestsConfigLookup:
    if not settings.package_tests_enabled:
        return PackageTestsConfigLookup()
    cached = _lookups_cache.get(package_name)
    if cached and cached[0] > time.monotonic():
        return cached[1]
    ttl = settings.package_tests_cache_ttl
    try:
        lookup = await _load_config(package_name)
    # Whatever goes wrong here, test results must still be processed
    except Exception as exc:
        url = _get_web_url(package_name)
        logging.exception('Cannot fetch tests config %s', url)
        # Not repr(): the one of aiohttp errors has the request headers, and
        # the lookup ends up in the public test results
        lookup = PackageTestsConfigLookup(
            url=url,
            error=f'Cannot fetch the config: {type(exc).__name__}: {exc}',
        )
        ttl = min(ttl, FAILED_FETCH_CACHE_TTL)
    _lookups_cache[package_name] = (time.monotonic() + ttl, lookup)
    return lookup


def collect_checks(result: dict) -> typing.Dict[str, bool]:
    """Map every check from the ALTS result to whether it has passed."""
    checks = {}
    for key, item in result.items():
        if key in SERVICE_RESULT_KEYS or not isinstance(item, dict):
            continue
        if key not in NESTED_RESULT_SECTIONS:
            checks[key] = bool(item.get('success', False))
            continue
        for name, check in item.items():
            if isinstance(check, dict):
                checks[name] = bool(check.get('success', False))
    return checks


def selects(test: str, check: str) -> bool:
    """Whether a test named in the config covers a check of ALTS result."""
    if test == 'third_party_tests':
        return check == THIRD_PARTY_WRAPPER or check.startswith(
            THIRD_PARTY_TEST_PREFIX
        )
    if test.startswith(THIRD_PARTY_TEST_PREFIX):
        return fnmatch.fnmatchcase(check, test)
    return check == test


def get_matched_rules(
    config: typing.Optional[PackageTestsConfig],
    package_name: str,
    platform_name: str,
    arch: str,
) -> MatchedRules:
    if not config:
        return MatchedRules()
    return config.get_rules(package_name, platform_name, arch)


def _get_reasons(
    rules: typing.Iterable[typing.Union[ExpectedFailureRule, SkipRule],],
    checks: typing.Iterable[str],
) -> typing.Dict[str, str]:
    """Map the checks covered by the rules to the reason of the first one."""
    reasons = {}
    for rule in rules:
        for test in rule.tests or ():
            for check in checks:
                if selects(test, check):
                    reasons.setdefault(check, rule.reason)
    return reasons


def evaluate_test_result(
    result: dict,
    rules: typing.Optional[MatchedRules] = None,
) -> ResultVerdict:
    rules = rules or MatchedRules()
    skipped = [
        {'test': test, 'reason': rule.reason}
        for rule in rules.skip
        for test in rule.tests or (ALL_TESTS,)
    ]
    # The package isn't tested at all, its test task got here only because
    # it had been created before the config said so
    if rules.skipped_package:
        return ResultVerdict(
            failed=False,
            skipped=skipped,
            expected_failures=[],
            unexpected_passes=[],
        )
    checks = collect_checks(result)
    skip_reasons = _get_reasons(rules.skip, checks)
    reasons = _get_reasons(rules.expected_failures, checks)
    failed = [name for name, passed in checks.items() if not passed]
    if THIRD_PARTY_WRAPPER in failed and any(
        name.startswith(THIRD_PARTY_TEST_PREFIX) for name in failed
    ):
        # Failed third-party tests make it fail, they decide on their own
        failed.remove(THIRD_PARTY_WRAPPER)
    failed = [name for name in failed if name not in skip_reasons]
    return ResultVerdict(
        failed=any(name not in reasons for name in failed),
        skipped=skipped,
        expected_failures=[
            {'test': name, 'reason': reasons[name]}
            for name in failed
            if name in reasons
        ],
        unexpected_passes=[
            name
            for name in reasons
            if checks[name] and name not in skip_reasons
        ],
    )

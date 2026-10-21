"""Schema of the per-package tests config kept in git.

Every package can have a repository named like its git.almalinux.org/rpms
one in the tests organization (git.almalinux.org/tests/<package>). Its
config file (see ``settings.package_tests_config_path``) tells ALBS which
ALTS tests not to run for the package and which of them are expected to
fail.
"""

import dataclasses
import fnmatch
import typing

from pydantic import (
    AfterValidator,
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
)
from typing_extensions import Annotated

__all__ = [
    'PACKAGE_TESTS',
    'THIRD_PARTY_TEST_PREFIX',
    'ExpectedFailureRule',
    'MatchedRules',
    'PackageTestsConfig',
    'SkipRule',
]


# Tests that ALTS runs for a package, named as in its results
PACKAGE_TESTS = (
    'install_package',
    'package_integrity_tests',
    'third_party_tests',
    'uninstall_package',
)
# Third-party tests are also addressed one by one, as ALTS names them:
# third_party_test_<test file>
THIRD_PARTY_TEST_PREFIX = 'third_party_test_'


def _check_test_name(name: str) -> str:
    is_third_party_test = name.startswith(THIRD_PARTY_TEST_PREFIX) and len(
        name
    ) > len(THIRD_PARTY_TEST_PREFIX)
    if name not in PACKAGE_TESTS and not is_third_party_test:
        raise ValueError(
            f'unknown test {name!r}, expected one of'
            f' {", ".join(PACKAGE_TESTS)} or {THIRD_PARTY_TEST_PREFIX}<file>'
        )
    return name


PackageTestName = Annotated[str, AfterValidator(_check_test_name)]


def _matches_any(value: str, patterns: typing.Optional[typing.List[str]]):
    # A filter that isn't set matches everything
    if patterns is None:
        return True
    return any(
        fnmatch.fnmatchcase(value.lower(), pattern.lower())
        for pattern in patterns
    )


class Rule(BaseModel):
    """Test tasks a rule applies to and why.

    ``packages``, ``platforms`` and ``arches`` are lists of shell-style
    patterns, matched case-insensitively against the binary package name,
    the ALBS platform name (e.g. AlmaLinux-9) and the build architecture.
    An omitted filter matches everything, so a rule without ``packages``
    covers all binary packages built from the source package.
    """

    # Unknown keys are typos far more often than features from the future,
    # so they invalidate the config instead of being silently ignored
    model_config = ConfigDict(extra='forbid')

    packages: typing.Optional[typing.List[str]] = Field(None, min_length=1)
    platforms: typing.Optional[typing.List[str]] = Field(None, min_length=1)
    arches: typing.Optional[typing.List[str]] = Field(None, min_length=1)
    reason: str

    @field_validator(
        'tests',
        'packages',
        'platforms',
        'arches',
        mode='before',
        check_fields=False,
    )
    @classmethod
    def single_value_to_list(cls, value):
        if isinstance(value, str):
            return [value]
        return value

    @field_validator('reason')
    @classmethod
    def reason_is_not_blank(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError('reason should explain the rule')
        return value

    def matches(self, package_name: str, platform_name: str, arch: str):
        return (
            _matches_any(package_name, self.packages)
            and _matches_any(platform_name, self.platforms)
            and _matches_any(arch, self.arches)
        )


class SkipRule(Rule):
    """Tests that aren't run, so their results never fail the test task.

    Without ``tests`` the packages aren't tested at all.
    """

    tests: typing.Optional[typing.List[PackageTestName]] = Field(
        None,
        min_length=1,
    )


class ExpectedFailureRule(Rule):
    """Tests that run, but their failures don't fail the test task."""

    tests: typing.List[PackageTestName] = Field(min_length=1)


@dataclasses.dataclass(frozen=True)
class MatchedRules:
    """Rules of a config that apply to one test task."""

    skip: typing.List[SkipRule] = dataclasses.field(default_factory=list)
    expected_failures: typing.List[ExpectedFailureRule] = dataclasses.field(
        default_factory=list
    )

    @property
    def skipped_package(self) -> typing.Optional[SkipRule]:
        """The rule that switches all tests of the package off, if any."""
        return next((rule for rule in self.skip if rule.tests is None), None)

    @property
    def skipped_tests(self) -> typing.List[str]:
        return list(
            dict.fromkeys(
                test for rule in self.skip for test in rule.tests or ()
            )
        )


class PackageTestsConfig(BaseModel):
    model_config = ConfigDict(extra='forbid')

    version: typing.Literal[1] = 1
    skip: typing.List[SkipRule] = []
    expected_failures: typing.List[ExpectedFailureRule] = []

    def get_rules(
        self,
        package_name: str,
        platform_name: str,
        arch: str,
    ) -> MatchedRules:
        def matching(rules: typing.List[Rule]) -> typing.List[Rule]:
            return [
                rule
                for rule in rules
                if rule.matches(package_name, platform_name, arch)
            ]

        return MatchedRules(
            skip=matching(self.skip),
            expected_failures=matching(self.expected_failures),
        )

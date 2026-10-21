import base64
import typing

import pytest

from alws.pulp_models import RpmPackage
from alws.utils import package_tests
from alws.utils.parsing import parse_rpm_nevra


@pytest.fixture
def mock_get_pulp_packages(monkeypatch):
    def func(*args, **kwargs):
        result = {}
        artifacts, *_ = args
        for artifact in artifacts:
            nevra = parse_rpm_nevra(artifact.name)
            result[artifact.href] = RpmPackage(
                name=nevra.name,
                epoch=nevra.epoch,
                version=nevra.version,
                release=nevra.release,
                arch=nevra.arch,
            )
        return result

    monkeypatch.setattr('alws.crud.test.get_pulp_packages', func)


def install_failed_result() -> dict:
    """ALTS result of a package that couldn't be installed."""
    return {
        'logs': [],
        'skipped_tests': [],
        'system_info': {'success': True},
        'install_package': {'success': False},
        'stop_environment': {'success': True},
        'initial_provision': {'success': True},
        'start_environment': {'success': True},
        'initialize_terraform': {'success': True},
    }


def passed_result() -> dict:
    """ALTS result of a package that has passed all tests."""
    return {
        **install_failed_result(),
        'install_package': {'success': True},
        'uninstall_package': {'success': True},
        'third_party_tests_wrapper': {'success': True},
    }


def gitea_contents_entry(package_name: str, content: str) -> dict:
    """What the Gitea contents API answers for a package tests config."""
    return {
        'type': 'file',
        'encoding': 'base64',
        'content': base64.b64encode(content.encode()).decode(),
        'html_url': (
            f'https://git.almalinux.org/tests/{package_name}'
            '/src/branch/main/alts.yaml'
        ),
        'last_commit_sha': 'c0ffee',
    }


class PackageTestsConfigs(dict):
    """Package tests configs a fake Gitea serves, by package name.

    A string is the content of the config, an exception is raised instead
    of answering, anything else is answered as is.
    """

    def __init__(self):
        super().__init__()
        # Packages Gitea has been asked about
        self.lookups = []

    def __setitem__(self, package_name: str, value: typing.Any):
        super().__setitem__(package_name, value)
        # Like a config pushed to git, but seen right away
        package_tests._lookups_cache.pop(package_name, None)


@pytest.fixture(autouse=True)
def package_tests_configs(
    monkeypatch,
) -> typing.Iterator[PackageTestsConfigs]:
    """Serve package tests configs from the yielded dict instead of Gitea.

    It's used by every test, so that none of them looks the configs up for
    real.
    """
    configs = PackageTestsConfigs()

    async def fetch_config_file(package_name: str):
        configs.lookups.append(package_name)
        if package_name not in configs:
            return None
        value = configs[package_name]
        if isinstance(value, Exception):
            raise value
        if isinstance(value, str):
            return gitea_contents_entry(package_name, value)
        return value

    monkeypatch.setattr(
        package_tests,
        '_fetch_config_file',
        fetch_config_file,
    )
    package_tests._lookups_cache.clear()
    yield configs
    package_tests._lookups_cache.clear()

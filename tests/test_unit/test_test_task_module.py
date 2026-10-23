import typing
import uuid

import pytest

from alws import models
from alws.crud.test import get_devel_only_packages, get_test_task_module
from alws.utils.pulp_utils import get_uuid_from_pulp_href

VERSION = '4.9.13'
RELEASE = '21.module_el8.10.0+4301+6cc0bb2f.3'


def rpm_module(name: str) -> models.RpmModule:
    return models.RpmModule(
        name=name,
        stream='client',
        version='8100020261016123248',
        context='94f01c65',
        arch='x86_64',
        pulp_href=f'/pulp/api/v3/content/rpm/modulemds/{uuid.uuid4()}/',
    )


def artifact(name: str, arch: str = 'x86_64') -> str:
    return f'{name}-0:{VERSION}-{RELEASE}.{arch}'


def build_task(*rpm_modules: models.RpmModule) -> models.BuildTask:
    return models.BuildTask(id=1, rpm_modules=list(rpm_modules))


def make_test_task(
    task: models.BuildTask,
    package_name: str,
) -> models.TestTask:
    return models.TestTask(
        build_task_id=task.id,
        build_task=task,
        package_name=package_name,
        package_version=VERSION,
        package_release=RELEASE,
    )


def module_of(
    task: models.BuildTask,
    package_name: str,
) -> typing.Optional[str]:
    module = get_test_task_module(
        make_test_task(task, package_name),
        get_devel_only_packages([task]),
    )
    return module.name if module else None


@pytest.fixture
def module_artifacts(monkeypatch) -> typing.Dict[str, typing.List[str]]:
    """Artifacts of modules in Pulp, by their pulp_href."""
    artifacts = {}

    def get_pulp_module_artifacts(rpm_modules):
        return {
            get_uuid_from_pulp_href(module.pulp_href): artifacts[
                module.pulp_href
            ]
            for module in rpm_modules
            if module.pulp_href in artifacts
        }

    monkeypatch.setattr(
        'alws.crud.test.get_pulp_module_artifacts',
        get_pulp_module_artifacts,
    )
    return artifacts


@pytest.fixture
def idm() -> models.RpmModule:
    return rpm_module('idm')


@pytest.fixture
def idm_devel() -> models.RpmModule:
    return rpm_module('idm-devel')


@pytest.fixture
def idm_build_task(
    module_artifacts,
    idm: models.RpmModule,
    idm_devel: models.RpmModule,
) -> models.BuildTask:
    module_artifacts[idm.pulp_href] = [
        artifact('ipa', arch='src'),
        artifact('ipa-client'),
        artifact('ipa-common', arch='noarch'),
    ]
    # ipa-server is filtered out of idm:client
    module_artifacts[idm_devel.pulp_href] = [
        artifact('ipa', arch='src'),
        artifact('ipa-server'),
        artifact('python3-ipaserver', arch='noarch'),
    ]
    return build_task(idm, idm_devel)


def test_package_of_module(idm_build_task):
    assert module_of(idm_build_task, 'ipa-client') == 'idm'
    assert module_of(idm_build_task, 'ipa-common') == 'idm'


def test_package_of_devel_module_only(idm_build_task):
    assert module_of(idm_build_task, 'ipa-server') == 'idm-devel'
    assert module_of(idm_build_task, 'python3-ipaserver') == 'idm-devel'


def test_package_of_both_modules(module_artifacts, idm, idm_devel):
    # Like a multilib package
    module_artifacts[idm.pulp_href] = [artifact('ipa-client', arch='i686')]
    module_artifacts[idm_devel.pulp_href] = [
        artifact('ipa-client', arch='i686'),
    ]
    assert module_of(build_task(idm, idm_devel), 'ipa-client') == 'idm'


def test_other_build_of_devel_package(idm_build_task):
    task = make_test_task(idm_build_task, 'ipa-server')
    task.package_release = '22.module_el8.10.0+4400+0123abcd'
    module = get_test_task_module(
        task,
        get_devel_only_packages([idm_build_task]),
    )
    assert module.name == 'idm'


def test_without_devel_module(module_artifacts, idm):
    module_artifacts[idm.pulp_href] = [artifact('ipa-client')]
    assert module_of(build_task(idm), 'ipa-server') == 'idm'


def test_non_modular_package(module_artifacts):
    assert get_devel_only_packages([build_task()]) == {}
    assert module_of(build_task(), 'ipa-server') is None


def test_pulp_failure(monkeypatch, idm, idm_devel):
    def get_pulp_module_artifacts(rpm_modules):
        raise ConnectionError('Pulp is down')

    monkeypatch.setattr(
        'alws.crud.test.get_pulp_module_artifacts',
        get_pulp_module_artifacts,
    )
    assert module_of(build_task(idm, idm_devel), 'ipa-server') == 'idm'

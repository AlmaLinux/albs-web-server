import uuid

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from alws import models
from alws.constants import BuildTaskStatus
from alws.constants import TestTaskStatus as TestStatus
from alws.crud.test import get_available_test_tasks
from alws.utils.pulp_utils import get_uuid_from_pulp_href
from tests.constants import ADMIN_USER_ID

pytestmark = pytest.mark.anyio

VERSION = '4.9.13'
RELEASE = '21.module_el8.10.0+4301+6cc0bb2f.3'
MODULE_VERSION = '8100020261016123248'


def rpm_module(name: str) -> models.RpmModule:
    return models.RpmModule(
        name=name,
        stream='client',
        version=MODULE_VERSION,
        context='94f01c65',
        arch='x86_64',
        pulp_href=f'/pulp/api/v3/content/rpm/modulemds/{uuid.uuid4()}/',
    )


@pytest.fixture
async def idm_test_tasks(async_session: AsyncSession, monkeypatch):
    """Tests of a package of idm:client and of one it filters out."""
    idm = rpm_module('idm')
    idm_devel = rpm_module('idm-devel')
    artifacts = {
        get_uuid_from_pulp_href(idm.pulp_href): [
            f'ipa-client-0:{VERSION}-{RELEASE}.x86_64',
        ],
        get_uuid_from_pulp_href(idm_devel.pulp_href): [
            f'ipa-server-0:{VERSION}-{RELEASE}.x86_64',
        ],
    }
    monkeypatch.setattr(
        'alws.crud.test.get_pulp_module_artifacts',
        lambda rpm_modules: artifacts,
    )
    build_task = models.BuildTask(
        build=models.Build(owner_id=ADMIN_USER_ID, mock_options={}),
        platform=models.Platform(
            name=f'test-task-modules-{uuid.uuid4().hex[:8]}',
            type='rpm',
            distr_type='rhel',
            distr_version='8',
            test_dist_name='almalinux',
            arch_list=['x86_64'],
            data={},
            modularity={},
        ),
        ref=models.BuildTaskRef(
            url='https://git.almalinux.org/rpms/ipa.git',
            git_ref='c8-stream-client',
            ref_type=4,
        ),
        status=BuildTaskStatus.COMPLETED,
        index=0,
        arch='x86_64',
        mock_options={},
        rpm_modules=[idm, idm_devel],
    )
    async_session.add_all([
        models.TestTask(
            build_task=build_task,
            package_name=package_name,
            package_version=VERSION,
            package_release=RELEASE,
            env_arch='x86_64',
            status=TestStatus.CREATED,
            revision=1,
        )
        for package_name in ('ipa-client', 'ipa-server')
    ])
    await async_session.commit()


async def test_devel_module_only_for_its_packages(
    async_session: AsyncSession,
    idm_test_tasks,
):
    payloads = await get_available_test_tasks(async_session)
    modules = {
        payload['package_name']: (
            payload['module_name'],
            payload['module_stream'],
            payload['module_version'],
        )
        for payload in payloads
    }
    assert modules == {
        'ipa-client': ('idm', 'client', MODULE_VERSION),
        'ipa-server': ('idm-devel', 'client', MODULE_VERSION),
    }

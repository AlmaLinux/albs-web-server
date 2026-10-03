from typing import List, Tuple

import pytest

from alws.utils.pulp_client import PulpClient
from tests.test_utils.pulp_utils import get_repo_href

TASK_HREF = '/pulp/api/v3/tasks/fd754c2e-3b6c-4d69-9417-6d7f5bdf1e28/'


@pytest.fixture
def pulp_requests(monkeypatch) -> List[Tuple[str, str, dict]]:
    requests = []
    repo_href = get_repo_href()

    async def request(_, method, endpoint, json=None, **kwargs):
        requests.append((method, endpoint, json))
        if method == 'POST':
            return {'pulp_href': repo_href}
        return {'task': TASK_HREF}

    async def wait_for_task(_, task_href, **kwargs):
        return {'pulp_href': task_href, 'state': 'completed'}

    async def create_rpm_distro(_, name, repository, **kwargs):
        return f'http://pulp/pulp/content/prod/{name}/'

    monkeypatch.setattr(PulpClient, 'request', request)
    monkeypatch.setattr(PulpClient, 'wait_for_task', wait_for_task)
    monkeypatch.setattr(PulpClient, 'create_rpm_distro', create_rpm_distro)
    return requests


def make_pulp_client() -> PulpClient:
    return PulpClient('http://pulp', 'admin', 'admin')


@pytest.mark.anyio
async def test_create_rpm_repository_without_layout(pulp_requests):
    await make_pulp_client().create_rpm_repository('almalinux-9-baseos')
    method, endpoint, payload = pulp_requests[0]
    assert (method, endpoint) == ('POST', 'pulp/api/v3/repositories/rpm/rpm/')
    assert 'layout' not in payload


@pytest.mark.anyio
async def test_create_rpm_repository_with_layout(pulp_requests):
    await make_pulp_client().create_rpm_repository(
        'almalinux-9-baseos',
        base_path_start='prod',
        layout='flat',
    )
    _, _, payload = pulp_requests[0]
    assert payload['layout'] == 'flat'


@pytest.mark.anyio
async def test_update_rpm_repository(pulp_requests):
    repo_href = get_repo_href()
    task = await make_pulp_client().update_rpm_repository(
        repo_href,
        layout='flat',
    )
    assert pulp_requests == [('PATCH', repo_href, {'layout': 'flat'})]
    assert task['pulp_href'] == TASK_HREF

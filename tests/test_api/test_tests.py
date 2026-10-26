import pytest

from alws.crud import test
from tests.mock_classes import BaseAsyncTestCase


class TestTestsEndpoints(BaseAsyncTestCase):
    async def test_get_available_test_tasks(
        self,
        build_done,
    ):
        response = await self.make_request(
            'get',
            '/api/v1/tests/get_test_tasks/',
        )
        assert response.json(), 'There is no available test tasks'

    @pytest.mark.parametrize(
        'endpoint, function',
        [
            ('build', 'restart_build_tests'),
            ('build_task', 'restart_build_task_tests'),
        ],
    )
    @pytest.mark.parametrize(
        'query, only_failed',
        [('', False), ('?only_failed=true', True)],
    )
    async def test_restart_tests(
        self,
        monkeypatch,
        endpoint: str,
        function: str,
        query: str,
        only_failed: bool,
    ):
        calls = []

        async def restart(db, entity_id, only_failed=False):
            calls.append((entity_id, only_failed))

        monkeypatch.setattr(test, function, restart)
        response = await self.make_request(
            'put',
            f'/api/v1/tests/{endpoint}/1/restart{query}',
        )
        assert response.status_code == 200, response.text
        assert calls == [(1, only_failed)]

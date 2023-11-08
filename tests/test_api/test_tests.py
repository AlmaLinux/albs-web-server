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

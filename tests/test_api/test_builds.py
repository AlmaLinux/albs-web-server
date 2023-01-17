from fastapi import status

from tests.mock_classes import BaseAsyncTestCase


class TestBuildsEndpoints(BaseAsyncTestCase):
    async def test_empty_tasks(self):
        response = await self.make_request(
            "post",
            "/api/v1/build_node/ping",
            json={"active_tasks": []},
        )
        message = "Empty active_tasks aren't pinged"
        self.assertEqual(response.status_code, status.HTTP_200_OK, message)

    async def test_ping(self):
        response = await self.make_request(
            "post",
            "/api/v1/build_node/ping",
            json={"active_tasks": [1, 2, 3]},
        )
        message = "Tasks aren't pinged"
        self.assertEqual(response.status_code, status.HTTP_200_OK, message)

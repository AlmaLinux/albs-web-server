import pytest

from alws.constants import BuildTaskStatus
from alws.models import Build
from tests.mock_classes import BaseAsyncTestCase


class TestBuildsEndpoints(BaseAsyncTestCase):
    @pytest.mark.parametrize("task_ids", [[1, 2, 3], []])
    async def test_ping(self, task_ids):
        response = await self.make_request(
            "post",
            "/api/v1/build_node/ping",
            json={"active_tasks": task_ids},
        )
        message = f"Cannot ping tasks:\n{response.text}"
        assert response.status_code == self.status_codes.HTTP_200_OK, message

    async def test_mark_build_as_cancelled(
        self,
        base_platform,
        base_product,
        regular_build: Build,
        start_build,
    ):
        response = await self.make_request(
            "patch",
            f"/api/v1/builds/{regular_build.id}/cancel",
        )
        message = f"Cannot cancel build:\n{response.text}"
        assert response.status_code == self.status_codes.HTTP_200_OK, message
        response = await self.make_request(
            "get",
            f"/api/v1/builds/{regular_build.id}/",
        )
        build = response.json()
        cancelled_tasks = [
            task
            for task in build["tasks"]
            if task["status"] == BuildTaskStatus.CANCELLED
        ]
        message = "Build doesn't contain cancelled tasks"
        assert cancelled_tasks, message

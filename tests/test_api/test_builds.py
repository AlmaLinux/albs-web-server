import pytest

from alws.constants import BuildTaskStatus
from alws.models import Build
from tests.constants import CUSTOM_USER_ID
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
            and task["error"] == "Build task cancelled by user"
        ]
        message = "Build doesn't contain cancelled tasks"
        assert cancelled_tasks, message

    async def test_create_modular_build(
        self,
        modular_build_payload,
    ):
        response = await self.make_request(
            "post",
            "/api/v1/builds/",
            json=modular_build_payload,
        )
        message = f"Cannot create modular build:\n{response.text}"
        assert response.status_code == self.status_codes.HTTP_200_OK, message

    async def test_create_modular_build_with_wrong_payload(
        self,
        nonvalid_modular_build_payload,
    ):
        response = await self.make_request(
            "post",
            "/api/v1/builds/",
            json=nonvalid_modular_build_payload,
        )
        assert response.status_code == self.status_codes.HTTP_400_BAD_REQUEST

    async def test_build_create_without_permissions(
        self,
        modular_build_payload,
    ):
        old_token = self.headers.pop("Authorization", None)
        token = BaseAsyncTestCase.generate_jwt_token(str(CUSTOM_USER_ID))
        response = await self.make_request(
            "post",
            "/api/v1/builds/",
            json=modular_build_payload,
            headers={
                "Authorization": f"Bearer {token}",
            },
        )
        assert response.status_code == self.status_codes.HTTP_403_FORBIDDEN
        self.headers["Authorization"] = old_token

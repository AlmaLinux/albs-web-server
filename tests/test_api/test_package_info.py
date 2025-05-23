import pytest

from fastapi import status

from alws.app import app
from tests.mock_classes import BaseAsyncTestCase


@pytest.mark.usefixtures(
    "patch_limiter"
)
class TestPackageInfoEndpoints(BaseAsyncTestCase):
    async def test_get_package_info_success(self, mock_get_package_info_success, package_info):
        response = await self.make_request(
            "get",
            "/api/v1/package_info/?name=example_package&almalinux_version=9",
        )

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data == package_info

    async def test_platform_not_found(self, mock_get_package_info_platform_not_found):
        response = await self.make_request(
            "get",
            "/api/v1/package_info/?name=bash&almalinux_version=999",
        )

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "Invalid distribution" in response.text

    async def test_repositories_not_found(self, mock_get_package_info_repos_not_found):
        response = await self.make_request(
            "get",
            "/api/v1/package_info/?name=bash&almalinux_version=9&arch=x86_64",
        )

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "No repositories found" in response.text


    async def test_empty_package_list(self, mock_get_package_info_empty):
        response = await self.make_request(
            "get",
            "/api/v1/package_info/?name=none&almalinux_version=9",
        )

        assert response.status_code == status.HTTP_200_OK
        assert response.json() == []

    async def test_missing_required_query_params(self):
        response = await self.make_request(
            "get",
            "/api/v1/package_info/?name=bash",
        )

        assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY

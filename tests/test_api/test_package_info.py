import pytest

from alws.app import app
from tests.mock_classes import BaseAsyncTestCase


@pytest.mark.usefixtures(
    "get_rpm_packages",
    "patch_limiter"
)
class TestPackageInfoEndpoints(BaseAsyncTestCase):
    async def test_get_package_info(self):
        response = await self.make_request(
            "get",
            "/api/v1/package_info/?package_name=example_package",
        )
        assert (
            response.status_code == self.status_codes.HTTP_200_OK
            and response.json()
        ), f"Cannot get package info by package name:\n{response.text}"

    async def test_get_package_info_version(self):
        version = 9
        not_version = 5

        response = await self.make_request(
            "get",
            f"/api/v1/package_info/?package_name=example_package&release_version={version}",
        )
        response_json = response.json()
        assert (
            response.status_code == self.status_codes.HTTP_200_OK
            and response_json
        ), f"Cannot get package info by package name and major version:\n{response.text}"
        assert (
            response_json[0]["release"]
            and f"el9" in response_json[0]["release"]
        )

        response = await self.make_request(
            "get",
            f"/api/v1/package_info/?package_name=example_package&release_version={not_version}",
        )
        assert (
            response.status_code == self.status_codes.HTTP_200_OK
            and not response.json()
        ), f"Cannot get package info by package name and major version:\n{response.text}"

    async def test_get_no_package_info(self):
        response = await self.make_request(
            "get",
            "/api/v1/package_info/?package_name=doesnt_exist",
        )
        assert (
            response.status_code == self.status_codes.HTTP_200_OK
            and not response.json()
        ), f"Error in fetching missing package:\n{response.text}"

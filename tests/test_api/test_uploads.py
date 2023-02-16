import pytest

from tests.mock_classes import BaseAsyncTestCase


@pytest.mark.usefixtures(
    "create_repo",
    "create_module_by_payload",
    "create_rpm_publication",
    "get_rpm_repo_by_params",
    "get_latest_version",
    "get_latest_repo_present_content",
    "get_latest_repo_removed_content",
    "get_by_href",
    "modify_repository",
    "upload_file",
)
class TestUploadsEndpoints(BaseAsyncTestCase):
    async def test_module_upload(
        self,
        modules_yaml,
        create_base_platform,
        repository: str = "almalinux-8-appstream-x86_64",
    ):
        response = await self.make_request(
            "post",
            "/api/v1/uploads/upload_repometada/",
            files={"modules": modules_yaml},
            data={"repository": repository},
        )
        message = f"Cannot upload module template:\n{response.text}"
        assert response.status_code == self.status_codes.HTTP_200_OK, message

    async def test_module_upload_build_repo(
        self,
        modules_yaml,
        create_base_platform,
        create_base_product,
        start_build,
        repository: str = "AlmaLinux-8-i686-1-br",
    ):
        response = await self.make_request(
            "post",
            "/api/v1/uploads/upload_repometada/",
            files={"modules": modules_yaml},
            data={"repository": repository},
        )
        message = f"Cannot upload module template:\n{response.text}"
        assert response.status_code == self.status_codes.HTTP_200_OK, message

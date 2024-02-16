import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from alws.models import BuildTask, RpmModule
from alws.utils.modularity import IndexWrapper

from tests.mock_classes import BaseAsyncTestCase


@pytest.mark.skip(
    reason=(
        "This test needs to be refactored because "
        "upload_repometadata is disabled, see "
        "https://github.com/AlmaLinux/build-system/issues/192"
    )
)
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
    async def test_module_upload_prod_repo(
        self,
        modules_yaml: bytes,
        base_platform,
    ):
        response = await self.make_request(
            "post",
            "/api/v1/uploads/upload_repometada/",
            files={"modules": modules_yaml},
            data={"repository": "almalinux-8-appstream-x86_64"},
        )
        message = f"Cannot upload module template:\n{response.text}"
        assert response.status_code == self.status_codes.HTTP_200_OK, message

    async def test_module_upload_build_repo(
        self,
        session: AsyncSession,
        modules_yaml: bytes,
        base_platform,
        base_product,
        modular_build,
        start_modular_build,
    ):
        response = await self.make_request(
            "post",
            "/api/v1/uploads/upload_repometada/",
            files={"modules": modules_yaml},
            data={"repository": "AlmaLinux-8-i686-1-br"},
        )
        message = f"Cannot upload module template:\n{response.text}"
        assert response.status_code == self.status_codes.HTTP_200_OK, message

        rpm_modules = (
            (
                await session.execute(
                    select(RpmModule).where(
                        RpmModule.id.in_(
                            select(BuildTask.rpm_module_id)
                            .where(
                                BuildTask.build_id == modular_build.id,
                                BuildTask.arch == "i686",
                            )
                            .scalar_subquery(),
                        )
                    )
                )
            )
            .scalars()
            .all()
        )
        if not rpm_modules:
            assert False, "rpm_modules not found"
        module_index = IndexWrapper.from_template(modules_yaml.decode())
        module = next(module_index.iter_modules())
        for rpm_module in rpm_modules:
            for attr in (
                "name",
                "version",
                "stream",
                "context",
                "arch",
            ):
                module_value = str(getattr(module, attr))
                db_module_value = str(getattr(rpm_module, attr))
                if module_value != db_module_value:
                    assert False, f"{module_value=} not equal to {db_module_value=}"

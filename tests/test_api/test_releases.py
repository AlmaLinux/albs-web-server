from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from alws import models
from alws.constants import ErrataPackageStatus, ReleaseStatus
from alws.crud.release import commit_release, revert_release
from tests.mock_classes import BaseAsyncTestCase


class TestReleasesEndpoints(BaseAsyncTestCase):
    async def test_get_releases(
        self,
    ):
        self.headers = {}
        response = await self.make_request("get", "/api/v1/releases/")
        message = f"Cannot retrieve releases:\n{response.text}"
        assert response.status_code == self.status_codes.HTTP_200_OK, message

    async def test_create_release(
        self,
        base_platform: models.Platform,
        base_product: models.Product,
        create_errata,
        build_done,
        build_for_release: models.Build,
        get_pulp_packages_info,
        disable_packages_check_in_prod_repos,
    ):
        payload = {
            "builds": [
                build_for_release.id,
            ],
            "build_tasks": [task.id for task in build_for_release.tasks],
            "platform_id": base_platform.id,
            "product_id": base_product.id,
        }
        response = await self.make_request(
            "post",
            "/api/v1/releases/new/",
            json=payload,
        )
        message = f"Cannot create release:\n{response.text}"
        assert response.status_code == self.status_codes.HTTP_200_OK, message

    async def test_create_community_release(
        self,
        base_platform: models.Platform,
        user_product: models.Product,
        modular_build_done,
        modular_build_for_release: models.Build,
        get_pulp_packages_info,
    ):
        payload = {
            "builds": [
                modular_build_for_release.id,
            ],
            "build_tasks": [
                task.id for task in modular_build_for_release.tasks
            ],
            "platform_id": base_platform.id,
            "product_id": user_product.id,
        }
        response = await self.make_request(
            "post",
            "/api/v1/releases/new/",
            json=payload,
        )
        message = f"Cannot create release:\n{response.text}"
        assert response.status_code == self.status_codes.HTTP_200_OK, message

    async def test_commit_release(
        self,
        session: AsyncSession,
        base_product: models.Product,
        disable_packages_check_in_prod_repos,
        disable_sign_verify,
        modify_repository,
        create_rpm_publication,
    ):
        response = await self.make_request(
            "get",
            "/api/v1/releases/",
        )
        message = f"Cannot retrieve releases:\n{response.text}"
        assert response.status_code == self.status_codes.HTTP_200_OK, message
        release_id = next(
            row
            for row in response.json()
            if row["product"]["id"] == base_product.id
        )["id"]
        response = await self.make_request(
            "post",
            f"/api/v1/releases/{release_id}/commit/",
        )
        message = f"Cannot commit release:\n{response.text}"
        assert response.status_code == self.status_codes.HTTP_200_OK, message
        await commit_release(session, release_id, self.user_id)
        response = await self.make_request(
            "get",
            f"/api/v1/releases/{release_id}/",
        )
        release = response.json()
        last_log = release["plan"]["last_log"]
        assert release["status"] == ReleaseStatus.COMPLETED, last_log

    async def test_commit_community_release(
        self,
        session: AsyncSession,
        user_product: models.Product,
        modify_repository,
        create_rpm_publication,
        get_repo_modules_yaml,
        create_module,
    ):
        response = await self.make_request(
            "get",
            "/api/v1/releases/",
        )
        message = f"Cannot retrieve releases:\n{response.text}"
        assert response.status_code == self.status_codes.HTTP_200_OK, message
        release_id = next(
            row
            for row in response.json()
            if row["product"]["id"] == user_product.id
        )["id"]
        response = await self.make_request(
            "post",
            f"/api/v1/releases/{release_id}/commit/",
        )
        message = f"Cannot commit release:\n{response.text}"
        assert response.status_code == self.status_codes.HTTP_200_OK, message
        await commit_release(session, release_id, self.user_id)
        response = await self.make_request(
            "get",
            f"/api/v1/releases/{release_id}/",
        )
        release = response.json()
        last_log = release["plan"]["last_log"]
        assert release["status"] == ReleaseStatus.COMPLETED, last_log

    async def test_get_release(
        self,
    ):
        self.headers = {}
        response = await self.make_request(
            "get",
            "/api/v1/releases/",
        )
        release_id = response.json()[0]["id"]
        response = await self.make_request(
            "get",
            f"/api/v1/releases/{release_id}/",
        )
        message = f"Cannot retrieve release:\n{response.text}"
        assert response.status_code == self.status_codes.HTTP_200_OK, message

    async def test_revert_release(
        self,
        session: AsyncSession,
        base_product: models.Product,
        modify_repository,
        create_rpm_publication,
    ):
        response = await self.make_request(
            "get",
            "/api/v1/releases/",
        )
        message = f"Cannot retrieve releases:\n{response.text}"
        assert response.status_code == self.status_codes.HTTP_200_OK, message
        release_id = next(
            row
            for row in response.json()
            if row["product"]["id"] == base_product.id
        )["id"]
        await revert_release(session, release_id, self.user_id)
        response = await self.make_request(
            "get",
            f"/api/v1/releases/{release_id}/",
        )
        release = response.json()
        last_log = release["plan"]["last_log"]
        assert release["status"] == ReleaseStatus.REVERTED, last_log
        builds = (
            (
                await session.execute(
                    select(models.Build).where(
                        models.Build.release_id == release_id,
                    ),
                )
            )
            .scalars()
            .all()
        )
        assert not builds, "Builds still has references to release"
        pulp_hrefs = [
            pkg_dict.get("package", {}).get("artifact_href", "")
            for pkg_dict in release["plan"].get("packages", [])
        ]
        errata_pkgs = await session.execute(
            select(models.NewErrataToALBSPackage).where(
                models.NewErrataToALBSPackage.status
                == ErrataPackageStatus.released,
                or_(
                    models.NewErrataToALBSPackage.pulp_href.in_(pulp_hrefs),
                    models.NewErrataToALBSPackage.albs_artifact_id.in_(
                        select(models.BuildTaskArtifact.id)
                        .where(
                            models.BuildTaskArtifact.href.in_(
                                pulp_hrefs,
                            ),
                        )
                        .scalar_subquery()
                    ),
                ),
            ),
        )
        errata_pkgs = errata_pkgs.scalars().all()
        assert not errata_pkgs, "Packages are not marked as proposal"

    async def test_revert_community_release(
        self,
        session: AsyncSession,
        user_product: models.Product,
        modify_repository,
        create_rpm_publication,
    ):
        response = await self.make_request(
            "get",
            "/api/v1/releases/",
        )
        message = f"Cannot retrieve releases:\n{response.text}"
        assert response.status_code == self.status_codes.HTTP_200_OK, message
        release_id = next(
            row
            for row in response.json()
            if row["product"]["id"] == user_product.id
        )["id"]
        await revert_release(session, release_id, self.user_id)
        response = await self.make_request(
            "get",
            f"/api/v1/releases/{release_id}/",
        )
        release = response.json()
        last_log = release["plan"]["last_log"]
        assert release["status"] == ReleaseStatus.REVERTED, last_log
        builds = (
            (
                await session.execute(
                    select(models.Build).where(
                        models.Build.release_id == release_id,
                    ),
                )
            )
            .scalars()
            .all()
        )
        assert not builds, "Builds still has references to release"
        product = (
            await self.make_request(
                "get",
                f"/api/v1/products/{user_product.id}/",
            )
        ).json()
        assert not [
            build
            for build in product["builds"]
            if build["id"] in release["build_ids"]
        ], "Product still has references to release"

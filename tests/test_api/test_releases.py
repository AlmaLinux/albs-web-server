import uuid

import pytest
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from alws import models
from alws.constants import ErrataPackageStatus, ReleaseStatus
from alws.crud.release import RELEASES_PER_PAGE, commit_release, revert_release
from tests.constants import ADMIN_USER_ID
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
        get_empty_module_from_pulp_db,
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
        async_session: AsyncSession,
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
        await commit_release(async_session, release_id, self.user_id)
        await async_session.commit()
        response = await self.make_request(
            "get",
            f"/api/v1/releases/{release_id}/",
        )
        release = response.json()
        last_log = release["plan"]["last_log"]
        assert release["status"] == ReleaseStatus.COMPLETED, last_log

    async def test_commit_community_release(
        self,
        async_session: AsyncSession,
        user_product: models.Product,
        modify_repository,
        create_rpm_publication,
        get_repo_modules_yaml,
        create_module,
        get_modules,
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
        await commit_release(async_session, release_id, self.user_id)
        await async_session.commit()
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

    async def test_get_build_releases(
        self,
    ):
        self.headers = {}
        response = await self.make_request(
            "get",
            "/api/v1/releases/",
        )
        release = response.json()[0]
        build_id = release["build_ids"][0]
        response = await self.make_request(
            "get",
            f"/api/v1/builds/{build_id}/releases/",
        )
        message = f"Cannot retrieve build releases:\n{response.text}"
        assert response.status_code == self.status_codes.HTTP_200_OK, message
        message = (
            f"Release {release['id']} is missing "
            f"among the releases of build {build_id}"
        )
        assert release["id"] in [row["id"] for row in response.json()], message

    async def test_revert_release(
        self,
        async_session: AsyncSession,
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
        await revert_release(async_session, release_id, self.user_id)
        await async_session.commit()
        response = await self.make_request(
            "get",
            f"/api/v1/releases/{release_id}/",
        )
        release = response.json()
        last_log = release["plan"]["last_log"]
        assert release["status"] == ReleaseStatus.REVERTED, last_log
        builds = (
            (
                await async_session.execute(
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
        errata_pkgs = await async_session.execute(
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
        async_session: AsyncSession,
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
        await revert_release(async_session, release_id, self.user_id)
        await async_session.commit()
        response = await self.make_request(
            "get",
            f"/api/v1/releases/{release_id}/",
        )
        release = response.json()
        last_log = release["plan"]["last_log"]
        assert release["status"] == ReleaseStatus.REVERTED, last_log
        builds = (
            (
                await async_session.execute(
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


class TestReleasesPagination(BaseAsyncTestCase):
    """GET /releases/ keeps both of its response shapes.

    Omitting pageNumber returns the bare list of every matching release, which
    API consumers rely on; passing it returns a ReleaseResponse page.
    """

    RELEASE_COUNT = 12

    @pytest.fixture
    async def isolated_releases(self, async_session: AsyncSession):
        """Fillers on a platform and product of their own.

        Releases are committed and the tables are module-scoped, so sharing
        base_platform/base_product here would put twelve empty releases at the
        top of the list that the other tests in this module read from.
        """
        suffix = uuid.uuid4().hex[:8]
        platform = models.Platform(
            name=f"release-paging-{suffix}",
            type="rpm",
            distr_type="rhel",
            distr_version="9",
            test_dist_name="almalinux",
            arch_list=["x86_64"],
            data={},
            modularity={},
        )
        product = models.Product(
            name=f"release-paging-product-{suffix}",
            title="release paging",
            owner_id=ADMIN_USER_ID,
            is_community=False,
        )
        async_session.add_all([platform, product])
        await async_session.flush()
        async_session.add_all([
            models.Release(
                build_ids=[],
                build_task_ids=[],
                platform_id=platform.id,
                product_id=product.id,
                owner_id=ADMIN_USER_ID,
                status=ReleaseStatus.SCHEDULED,
                plan={"packages": [], "repositories": []},
            )
            for _ in range(self.RELEASE_COUNT)
        ])
        await async_session.commit()
        return platform.id

    async def test_releases_without_page_returns_full_list(
        self,
        isolated_releases: int,
    ):
        response = await self.make_request(
            "get",
            f"/api/v1/releases/?platform_id={isolated_releases}",
        )
        message = f"Cannot retrieve releases:\n{response.text}"
        assert response.status_code == self.status_codes.HTTP_200_OK, message
        payload = response.json()

        message = (
            "Omitting pageNumber must keep returning a bare list of "
            f"releases, got {type(payload).__name__}"
        )
        assert isinstance(payload, list), message
        assert len(payload) == self.RELEASE_COUNT

    async def test_releases_with_page_returns_one_page(
        self,
        isolated_releases: int,
    ):
        response = await self.make_request(
            "get",
            f"/api/v1/releases/?platform_id={isolated_releases}&pageNumber=2",
        )
        assert response.status_code == self.status_codes.HTTP_200_OK
        payload = response.json()
        assert isinstance(payload, dict)
        message = "Second page must hold the releases left after the first"
        assert (
            len(payload["releases"]) == self.RELEASE_COUNT - RELEASES_PER_PAGE
        ), message
        assert payload["current_page"] == 2
        message = "total_releases must still count every matching release"
        assert payload["total_releases"] == self.RELEASE_COUNT, message

    @pytest.mark.parametrize("page_number", [0, -5])
    async def test_releases_clamp_pages_below_the_first(
        self,
        isolated_releases: int,
        page_number: int,
    ):
        response = await self.make_request(
            "get",
            f"/api/v1/releases/?platform_id={isolated_releases}"
            f"&pageNumber={page_number}",
        )
        assert response.status_code == self.status_codes.HTTP_200_OK
        payload = response.json()
        assert isinstance(payload, dict)
        assert len(payload["releases"]) == RELEASES_PER_PAGE
        assert payload["current_page"] == 1

import pytest
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from alws.constants import BuildTaskStatus
from alws.crud.build import BUILDS_PER_PAGE
from alws.models import Build, BuildTask, BuildTaskArtifact, BuildTaskRef
from alws.utils.modularity import IndexWrapper
from alws.utils.pulp_client import PulpClient
from tests.constants import ADMIN_USER_ID, CUSTOM_USER_ID
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

    async def test_get_builds_per_page(
        self,
        regular_build: Build,
        start_build,
    ):
        response = await self.make_request(
            "get",
            "/api/v1/builds/?pageNumber=1",
        )
        message = f"Cannot get builds:\n{response.text}"
        assert response.status_code == self.status_codes.HTTP_200_OK, message
        payload = response.json()
        assert payload["current_page"] == 1
        assert payload["total_builds"] >= 1
        assert len(payload["builds"]) <= 10
        build_ids = [build["id"] for build in payload["builds"]]
        assert regular_build.id in build_ids
        message = "Builds are not sorted by id descending"
        assert build_ids == sorted(build_ids, reverse=True), message
        build = payload["builds"][build_ids.index(regular_build.id)]
        assert build["tasks"], "Build tasks are not loaded"
        assert build["owner"]["id"] == regular_build.owner_id

    async def test_get_builds_per_page_out_of_range(
        self,
        regular_build: Build,
        start_build,
    ):
        response = await self.make_request(
            "get",
            "/api/v1/builds/?pageNumber=1000",
        )
        message = f"Cannot get builds:\n{response.text}"
        assert response.status_code == self.status_codes.HTTP_200_OK, message
        payload = response.json()
        assert payload["builds"] == []
        assert payload["current_page"] == 1000
        message = "An out of range page must not affect the total"
        assert payload["total_builds"] >= 1, message

    @pytest.mark.parametrize(
        "query, expected",
        [
            ("project=chan", True),
            ("project=definitely-not-a-project", False),
            ("ref=c8", True),
            ("ref=definitely-not-a-ref", False),
            ("build_task_arch=x86_64", True),
            ("build_task_arch=s390x", False),
            ("released=false", True),
            ("released=true", False),
            ("is_running=true", True),
            ("is_running=false", False),
        ],
    )
    async def test_get_builds_filters(
        self,
        regular_build: Build,
        start_build,
        query: str,
        expected: bool,
    ):
        response = await self.make_request(
            "get",
            f"/api/v1/builds/?pageNumber=1&{query}",
        )
        message = f"Cannot get builds by {query}:\n{response.text}"
        assert response.status_code == self.status_codes.HTTP_200_OK, message
        payload = response.json()
        found = regular_build.id in [
            build["id"] for build in payload["builds"]
        ]
        message = f"Build is {'missing from' if expected else 'in'} {query}"
        assert found is expected, message
        if expected:
            message = f"total_builds does not match the page for {query}"
            assert payload["total_builds"] >= len(payload["builds"]), message

    async def test_get_builds_by_created_by(
        self,
        regular_build: Build,
        start_build,
    ):
        for created_by, expected in ((ADMIN_USER_ID, True), (99999, False)):
            response = await self.make_request(
                "get",
                f"/api/v1/builds/?pageNumber=1&created_by={created_by}",
            )
            message = f"Cannot get builds by {created_by=}:\n{response.text}"
            assert response.status_code == self.status_codes.HTTP_200_OK, (
                message
            )
            payload = response.json()
            found = regular_build.id in [
                build["id"] for build in payload["builds"]
            ]
            assert found is expected, f"Unexpected result for {created_by=}"

    async def test_get_builds_by_platform_id(
        self,
        regular_build: Build,
        start_build,
    ):
        response = await self.make_request(
            "get",
            f"/api/v1/builds/{regular_build.id}/",
        )
        assert response.status_code == self.status_codes.HTTP_200_OK
        platform_id = response.json()["tasks"][0]["platform"]["id"]

        for value, expected in ((platform_id, True), (99999, False)):
            response = await self.make_request(
                "get",
                f"/api/v1/builds/?pageNumber=1&platform_id={value}",
            )
            message = f"Cannot get builds by platform_id={value}"
            assert response.status_code == self.status_codes.HTTP_200_OK, (
                message
            )
            found = regular_build.id in [
                build["id"] for build in response.json()["builds"]
            ]
            assert found is expected, f"Unexpected result for {value=}"

    async def test_get_builds_by_signed(
        self,
        regular_build: Build,
        start_build,
    ):
        for signed, expected in (("false", True), ("true", False)):
            response = await self.make_request(
                "get",
                f"/api/v1/builds/?pageNumber=1&signed={signed}",
            )
            assert response.status_code == self.status_codes.HTTP_200_OK
            found = regular_build.id in [
                build["id"] for build in response.json()["builds"]
            ]
            assert found is expected, f"Unexpected result for {signed=}"

    async def test_get_builds_by_rpm_params(
        self,
        async_session: AsyncSession,
        build_done,
        regular_build: Build,
        monkeypatch,
    ):
        """
        The rpm_* filters resolve package hrefs through Pulp and then match
        them against build_artifacts, so Pulp answers with the hrefs that are
        really in the database.
        """
        hrefs = (
            (
                await async_session.execute(
                    select(BuildTaskArtifact.href)
                    .join(
                        BuildTask,
                        BuildTask.id == BuildTaskArtifact.build_task_id,
                    )
                    .where(
                        BuildTask.build_id == regular_build.id,
                        BuildTaskArtifact.type == "rpm",
                    )
                )
            )
            .scalars()
            .all()
        )
        assert hrefs, "The build has no rpm artifacts to match against"

        asked = []

        async def get_rpm_packages(self, **params):
            asked.append(params)
            if params.get("name") == "chan":
                return [{"pulp_href": href} for href in hrefs]
            return []

        monkeypatch.setattr(
            PulpClient, "get_rpm_packages", get_rpm_packages
        )

        for query, expected in (
            ("rpm_name=chan", True),
            ("rpm_name=nosuchpackage", False),
            ("rpm_name=chan&rpm_arch=x86_64&rpm_version=0.0.4", True),
        ):
            asked.clear()
            response = await self.make_request(
                "get",
                f"/api/v1/builds/?pageNumber=1&{query}",
            )
            message = f"Cannot get builds by {query}:\n{response.text}"
            assert response.status_code == self.status_codes.HTTP_200_OK, (
                message
            )
            found = regular_build.id in [
                build["id"] for build in response.json()["builds"]
            ]
            assert found is expected, f"Unexpected result for {query}"
            message = f"Pulp was asked {len(asked)} times for {query}"
            assert len(asked) == 1, message

    async def test_get_builds_does_not_query_pulp_without_rpm_params(
        self,
        regular_build: Build,
        start_build,
        monkeypatch,
    ):
        async def get_rpm_packages(self, **params):
            raise AssertionError("Pulp must not be queried without rpm_*")

        monkeypatch.setattr(
            PulpClient, "get_rpm_packages", get_rpm_packages
        )
        response = await self.make_request(
            "get",
            "/api/v1/builds/?pageNumber=1",
        )
        assert response.status_code == self.status_codes.HTTP_200_OK

    async def test_get_builds_page_size(
        self,
        async_session: AsyncSession,
        regular_build: Build,
        start_build,
    ):
        """
        albs-frontend computes its pager as total_builds / 10 (BuildFeed.vue),
        so the page size is part of the API contract and not a free knob.
        """
        template = (
            await async_session.execute(
                select(Build.team_id, BuildTask.platform_id)
                .join(BuildTask, BuildTask.build_id == Build.id)
                .limit(1)
            )
        ).first()
        assert template is not None, "No build task to copy the platform from"
        team_id, platform_id = template

        for number in range(15):
            build = Build(owner_id=ADMIN_USER_ID, team_id=team_id,
                          mock_options={})
            async_session.add(build)
            await async_session.flush()
            task_ref = BuildTaskRef(
                url=f"https://git.almalinux.org/rpms/filler{number}.git",
                git_ref=f"a{number}",
                ref_type=4,
            )
            async_session.add(task_ref)
            await async_session.flush()
            async_session.add(
                BuildTask(
                    build_id=build.id,
                    platform_id=platform_id,
                    ref_id=task_ref.id,
                    status=0,
                    index=0,
                    arch="aarch64",
                    mock_options={},
                )
            )
        await async_session.commit()

        pages = []
        for page_number in (1, 2):
            response = await self.make_request(
                "get",
                f"/api/v1/builds/?pageNumber={page_number}",
            )
            message = f"Cannot get page {page_number}:\n{response.text}"
            assert response.status_code == self.status_codes.HTTP_200_OK, (
                message
            )
            pages.append(response.json())

        assert len(pages[0]["builds"]) == BUILDS_PER_PAGE == 10
        assert len(pages[1]["builds"]) == BUILDS_PER_PAGE == 10
        first, second = (
            [build["id"] for build in page["builds"]] for page in pages
        )
        assert not set(first) & set(second), "Pages overlap"
        message = "Page 2 is not the continuation of page 1"
        assert min(first) > max(second), message
        assert pages[0]["total_builds"] == pages[1]["total_builds"]
        message = "total_builds is smaller than the builds already listed"
        assert pages[0]["total_builds"] >= len(first) + len(second), message

    # @pytest.mark.skip(reason="Checking the reason for freezing tests")
    async def test_build_delete(
        self,
        create_errata,
        build_done,
        build_for_release,
        delete_by_href,
    ):
        response = await self.make_request(
            "delete",
            f"/api/v1/builds/{build_for_release.id}/remove",
        )
        assert response.status_code == self.status_codes.HTTP_204_NO_CONTENT


@pytest.mark.usefixtures(
    "get_multilib_packages_from_pulp",
    "enable_beholder",
    "mock_beholder_call",
)
class TestModularBuilds(BaseAsyncTestCase):
    async def test_multilib_virt(
        self,
        multilib_virt_with_artifacts: str,
        modules_artifacts: dict,
        virt_modular_build: Build,
        get_empty_module_from_pulp_db,
        virt_build_done,
        tmp_path,
    ):
        index_with_artifacts = IndexWrapper.from_template(
            multilib_virt_with_artifacts,
        )

        module_files = [
            tmp_path / f"modules.{module.name}-{module.arch}.yaml"
            for module in index_with_artifacts.iter_modules()
        ]

        for module_file in module_files:
            build_index = IndexWrapper.from_template(module_file.read_text())
            for build_module in build_index.iter_modules():
                module = index_with_artifacts.get_module(
                    build_module.name,
                    build_module.stream,
                )
                assert (
                    build_module.get_rpm_artifacts()
                    == module.get_rpm_artifacts()
                )

        for arch in ["i686", "ppc64le"]:
            for module in index_with_artifacts.iter_modules():
                module_file = tmp_path / f"modules.{module.name}-{arch}.yaml"
                build_index = IndexWrapper.from_template(
                    module_file.read_text()
                )
                for build_module in build_index.iter_modules():
                    artifacts = modules_artifacts[f"{build_module.name}:{arch}"]
                    assert build_module.get_rpm_artifacts() == artifacts

    async def test_multilib_ruby(
        self,
        multilib_ruby_with_artifacts: str,
        modules_artifacts: dict,
        ruby_modular_build: Build,
        get_empty_module_from_pulp_db,
        ruby_build_done,
        tmp_path,
    ):
        index_with_artifacts = IndexWrapper.from_template(
            multilib_ruby_with_artifacts,
        )

        module_files = [
            tmp_path / f"modules.{module.name}-{module.arch}.yaml"
            for module in index_with_artifacts.iter_modules()
        ]

        for module_file in module_files:
            build_index = IndexWrapper.from_template(module_file.read_text())
            for build_module in build_index.iter_modules():
                module = index_with_artifacts.get_module(
                    build_module.name,
                    build_module.stream,
                )
                assert (
                    build_module.get_rpm_artifacts()
                    == module.get_rpm_artifacts()
                )

        for arch in ["i686", "aarch64"]:
            for module in index_with_artifacts.iter_modules():
                module_file = tmp_path / f"modules.{module.name}-{arch}.yaml"
                build_index = IndexWrapper.from_template(
                    module_file.read_text()
                )
                for build_module in build_index.iter_modules():
                    artifacts = modules_artifacts[f"{build_module.name}:{arch}"]
                    assert build_module.get_rpm_artifacts() == artifacts

    async def test_multilib_subversion(
        self,
        multilib_subversion_with_artifacts: str,
        modules_artifacts: dict,
        subversion_modular_build: Build,
        get_empty_module_from_pulp_db,
        subversion_build_done,
        tmp_path,
    ):
        index_with_artifacts = IndexWrapper.from_template(
            multilib_subversion_with_artifacts,
        )

        module_files = [
            tmp_path / f"modules.{module.name}-{module.arch}.yaml"
            for module in index_with_artifacts.iter_modules()
        ]

        for module_file in module_files:
            build_index = IndexWrapper.from_template(module_file.read_text())
            for build_module in build_index.iter_modules():
                module = index_with_artifacts.get_module(
                    build_module.name,
                    build_module.stream,
                )
                assert (
                    build_module.get_rpm_artifacts()
                    == module.get_rpm_artifacts()
                )
        for arch in ["i686", "aarch64"]:
            for module in index_with_artifacts.iter_modules():
                module_file = tmp_path / f"modules.{module.name}-{arch}.yaml"
                build_index = IndexWrapper.from_template(
                    module_file.read_text()
                )
                for build_module in build_index.iter_modules():
                    artifacts = modules_artifacts[f"{build_module.name}:{arch}"]
                    assert build_module.get_rpm_artifacts() == artifacts

    async def test_multilib_llvm(
        self,
        multilib_llvm_with_artifacts: str,
        modules_artifacts: dict,
        llvm_modular_build: Build,
        get_empty_module_from_pulp_db,
        llvm_build_done,
        tmp_path,
    ):
        index_with_artifacts = IndexWrapper.from_template(
            multilib_llvm_with_artifacts,
        )
        module_files = [
            tmp_path / f"modules.{module.name}-{module.arch}.yaml"
            for module in index_with_artifacts.iter_modules()
        ]

        for module_file in module_files:
            build_index = IndexWrapper.from_template(module_file.read_text())
            for build_module in build_index.iter_modules():
                module = index_with_artifacts.get_module(
                    build_module.name,
                    build_module.stream,
                )
                assert (
                    build_module.get_rpm_artifacts()
                    == module.get_rpm_artifacts()
                )

        for module in index_with_artifacts.iter_modules():
            module_file = tmp_path / f"modules.{module.name}-i686.yaml"
            build_index = IndexWrapper.from_template(module_file.read_text())
            for build_module in build_index.iter_modules():
                artifacts = modules_artifacts[f"{build_module.name}:i686"]
                assert build_module.get_rpm_artifacts() == artifacts

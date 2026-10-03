import pytest
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession

from alws import models
from alws.constants import SignStatus
from alws.crud.sign_task import get_available_sign_task
from tests.constants import ADMIN_USER_ID


@pytest.mark.anyio
class TestGetAvailableSignTask:

    @pytest.fixture
    async def multi_platform_sign_task(
        self,
        async_session: AsyncSession,
        base_platform: models.Platform,
        sign_key: models.SignKey,
    ):
        second_platform = models.Platform(
            name="Test-Sign-Platform",
            type="rpm",
            distr_type="rhel",
            distr_version="10",
            test_dist_name="test",
            arch_list=["x86_64"],
            data={},
        )
        async_session.add(second_platform)
        await async_session.flush()

        repos = [
            models.Repository(
                name=f"test-sign-repo-{platform.id}-{arch}",
                arch=arch,
                url=f"http://example.com/{platform.id}-{arch}/",
                type="rpm",
                debug=False,
                production=False,
                platform_id=platform.id,
            )
            for platform in (base_platform, second_platform)
            for arch in ("src", "x86_64")
        ]
        build = models.Build(
            owner_id=ADMIN_USER_ID,
            mock_options={},
            repos=repos,
        )
        build_tasks = {}
        for platform in (base_platform, second_platform):
            ref = models.BuildTaskRef(url="http://example.com/test.git")
            async_session.add(ref)
            await async_session.flush()
            build_task = models.BuildTask(
                build=build,
                platform_id=platform.id,
                ref_id=ref.id,
                status=0,
                index=0,
                arch="x86_64",
                mock_options={},
            )
            build_tasks[platform.id] = build_task
            async_session.add(build_task)
        async_session.add(build)
        await async_session.flush()

        source_rpms = []
        binary_rpms = []
        for platform in (base_platform, second_platform):
            build_task = build_tasks[platform.id]
            src_artifact = models.BuildTaskArtifact(
                build_task_id=build_task.id,
                name=f"test-package-{platform.id}-1.0-1.src.rpm",
                type="rpm",
                href=f"test-src-href-{platform.id}",
            )
            binary_artifact = models.BuildTaskArtifact(
                build_task_id=build_task.id,
                name=f"test-package-{platform.id}-1.0-1.x86_64.rpm",
                type="rpm",
                href=f"test-binary-href-{platform.id}",
            )
            async_session.add_all([src_artifact, binary_artifact])
            await async_session.flush()
            source_rpm = models.SourceRpm(
                build_id=build.id,
                artifact_id=src_artifact.id,
            )
            async_session.add(source_rpm)
            await async_session.flush()
            binary_rpm = models.BinaryRpm(
                build_id=build.id,
                artifact_id=binary_artifact.id,
                source_rpm_id=source_rpm.id,
            )
            async_session.add(binary_rpm)
            source_rpms.append(source_rpm)
            binary_rpms.append(binary_rpm)

        sign_task = models.SignTask(
            build_id=build.id,
            sign_key_id=sign_key.id,
            status=SignStatus.IDLE,
        )
        async_session.add(sign_task)
        await async_session.commit()

        yield {
            "sign_key": sign_key,
            "platforms": (base_platform, second_platform),
            "build": build,
        }

        repo_ids = [repo.id for repo in repos]
        await async_session.execute(delete(models.BinaryRpm))
        await async_session.execute(delete(models.SourceRpm))
        await async_session.execute(delete(models.BuildTaskArtifact))
        await async_session.execute(delete(models.SignTask))
        await async_session.execute(delete(models.BuildTask))
        await async_session.execute(delete(models.BuildTaskRef))
        await async_session.execute(delete(models.BuildRepo))
        await async_session.execute(
            delete(models.Repository).where(
                models.Repository.id.in_(repo_ids)
            )
        )
        await async_session.execute(
            delete(models.Build).where(models.Build.id == build.id)
        )
        await async_session.execute(
            delete(models.Platform).where(
                models.Platform.id == second_platform.id
            )
        )
        await async_session.commit()

    async def test_payload_contains_platform_info(
        self,
        async_session: AsyncSession,
        multi_platform_sign_task,
    ):
        sign_key = multi_platform_sign_task["sign_key"]
        platforms = multi_platform_sign_task["platforms"]
        platform_names = {p.id: p.name for p in platforms}

        payload = await get_available_sign_task(
            async_session, [sign_key.keyid]
        )

        assert payload, "No sign task payload returned"
        packages = payload["packages"]
        # one source and one binary RPM per platform
        assert len(packages) == 4
        src_platforms = set()
        binary_platforms = set()
        for package in packages:
            assert package["platform_id"] in platform_names
            assert (
                package["platform_name"]
                == platform_names[package["platform_id"]]
            )
            if package["arch"] == "src":
                src_platforms.add(package["platform_id"])
            else:
                binary_platforms.add(package["platform_id"])
        expected_platform_ids = set(platform_names)
        assert src_platforms == expected_platform_ids
        assert binary_platforms == expected_platform_ids

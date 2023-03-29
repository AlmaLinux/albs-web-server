import pytest

from alws.release_planner import AlmaLinuxReleasePlanner, BaseReleasePlanner
from tests.test_utils.pulp_utils import get_rpm_pkg_info


@pytest.mark.anyio
@pytest.fixture
async def get_pulp_packages_info(monkeypatch):
    async def func(*args, **kwargs):
        _, build_rpms, build_tasks, *_ = args
        return [
            get_rpm_pkg_info(rpm.artifact)
            for rpm in build_rpms
            if build_tasks and rpm.artifact.build_task_id in build_tasks
        ]

    monkeypatch.setattr(BaseReleasePlanner, "get_pulp_packages_info", func)


@pytest.fixture
def disable_packages_check_in_prod_repos(monkeypatch):
    def func(*args, **kwargs):
        return []

    monkeypatch.setattr(
        "alws.release_planner.get_rpm_packages_from_repositories",
        func,
    )


@pytest.mark.anyio
@pytest.fixture
async def disable_sign_verify(monkeypatch):
    async def func(*args, **kwargs):
        return True

    monkeypatch.setattr(
        "alws.release_planner.sign_task.verify_signed_build",
        func,
    )


@pytest.fixture(autouse=True)
def mock_get_packages_from_64_bit_repos(monkeypatch):
    def func(*args, **kwargs):
        return []

    monkeypatch.setattr(
        "alws.release_planner.get_rpm_packages_from_repository",
        func,
    )

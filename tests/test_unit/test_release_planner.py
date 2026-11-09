import datetime

import pytest

from alws.release_planner import AlmaLinuxReleasePlanner
from alws.utils.measurements import measure_stage, record_stage

pytestmark = pytest.mark.anyio


async def test_get_modules_templates_downloads_each_repo_once():
    planner = AlmaLinuxReleasePlanner(db=None)
    requested = []
    error = RuntimeError("pulp is down")

    async def get_repo_modules_yaml(url: str):
        requested.append(url)
        if url == "broken":
            raise error
        return f"template of {url}"

    planner.pulp_client.get_repo_modules_yaml = get_repo_modules_yaml

    templates = await planner.get_modules_templates(
        ["x86_64", "broken", "aarch64", "x86_64"],
    )

    assert sorted(requested) == ["aarch64", "broken", "x86_64"]
    assert templates == {
        "x86_64": "template of x86_64",
        "broken": error,
        "aarch64": "template of aarch64",
    }


def test_measure_stage_sums_up_repeated_runs():
    stats = {}
    first_start = datetime.datetime.utcnow() - datetime.timedelta(seconds=2)
    record_stage(stats, "beholder_requests", first_start)
    with measure_stage(stats, "beholder_requests"):
        pass

    stage = stats["beholder_requests"]
    assert stage["start_ts"] == first_start.isoformat()
    assert stage["delta_ts"] >= 2
    assert stage["finish_ts"] >= stage["start_ts"]

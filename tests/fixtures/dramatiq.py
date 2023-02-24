import pytest

from alws.dramatiq.build import _start_build
from alws.models import Build
from alws.schemas.build_schema import BuildCreate


@pytest.fixture(autouse=True)
def patch_dramatiq_actor_send(monkeypatch):
    def func(*args, **kwargs):
        return

    monkeypatch.setattr("dramatiq.Actor.send", func)


@pytest.mark.anyio
@pytest.fixture
async def start_build(
    modular_build: Build,
    modular_build_payload: dict,
    create_module,
    create_build_rpm_repo,
    create_log_repo,
    modify_repository,
):
    await _start_build(modular_build.id, BuildCreate(**modular_build_payload))

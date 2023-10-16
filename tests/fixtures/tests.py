import pytest

from alws.pulp_models import RpmPackage
from alws.utils.parsing import parse_rpm_nevra


@pytest.fixture
def mock_get_pulp_packages(monkeypatch):
    def func(*args, **kwargs):
        result = {}
        artifacts, *_ = args
        for artifact in artifacts:
            nevra = parse_rpm_nevra(artifact.name)
            result[artifact.href] = RpmPackage(
                name=nevra.name,
                epoch=nevra.epoch,
                version=nevra.version,
                release=nevra.release,
                arch=nevra.arch,
            )
        return result

    monkeypatch.setattr('alws.crud.test.get_pulp_packages', func)

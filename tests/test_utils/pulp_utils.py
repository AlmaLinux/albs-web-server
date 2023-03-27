import uuid

from alws.schemas.build_node_schema import BuildDoneArtifact
from alws.utils.parsing import parse_rpm_nevra


def get_repo_href() -> str:
    return f"/pulp/api/v3/repositories/rpm/rpm/{uuid.uuid4()}/"


def get_latest_repo_version(repo_href: str) -> str:
    return f"{repo_href}versions/1/"


def get_module_href() -> str:
    return f"/pulp/api/v3/content/rpm/modulemds/{uuid.uuid4()}/"


def get_module_defaults_href() -> str:
    return f"/pulp/api/v3/content/rpm/modulemd_defaults/{uuid.uuid4()}/"


def get_artifact_href() -> str:
    return f"/pulp/api/v3/artifacts/{uuid.uuid4()}/"


def get_file_href() -> str:
    return f"/pulp/api/v3/content/file/files/{uuid.uuid4()}/"


def get_rpm_pkg_href() -> str:
    return f"/pulp/api/v3/content/rpm/packages/{uuid.uuid4()}/"


def get_modules_href() -> str:
    return f"/pulp/api/v3/content/rpm/modulemds/{uuid.uuid4()}/"


def get_rpm_pkg_info(artifact: BuildDoneArtifact):
    nevra = parse_rpm_nevra(artifact.name)
    rpm_sourcerpm = f"{nevra.name}-{nevra.version}-{nevra.release}.src.rpm"
    pkg_info = {
        "pulp_href": artifact.href,
        "name": nevra.name,
        "epoch": nevra.epoch,
        "version": nevra.version,
        "release": nevra.release,
        "arch": nevra.arch,
        "rpm_sourcerpm": rpm_sourcerpm,
    }
    return pkg_info

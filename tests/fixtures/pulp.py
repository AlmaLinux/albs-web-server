import asyncio
import hashlib
import re
import uuid

import pytest

from alws.config import settings
from alws.schemas.build_node_schema import BuildDoneArtifact
from alws.utils.modularity import IndexWrapper
from alws.utils.parsing import parse_rpm_nevra
from alws.utils.pulp_client import PulpClient


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


@pytest.fixture(autouse=True)
def semaphore_patch(monkeypatch):
    monkeypatch.setattr(
        "alws.utils.pulp_client.PULP_SEMAPHORE",
        asyncio.Semaphore(5),
    )


@pytest.fixture
def create_repo(monkeypatch):
    async def func(*args, **kwargs):
        repo_url = "mock_url"
        repo_href = get_repo_href()
        return repo_url, repo_href

    monkeypatch.setattr(PulpClient, "create_rpm_repository", func)


@pytest.fixture
def get_latest_version(monkeypatch):
    async def func(_, repo_href: str):
        return get_latest_repo_version(repo_href)

    monkeypatch.setattr(PulpClient, "get_repo_latest_version", func)


@pytest.fixture
def get_latest_repo_present_content(monkeypatch):
    async def func(_, repo_version: str):
        return {
            "rpm.package": {
                "count": 5517,
                "href": f"/pulp/api/v3/content/rpm/packages/?repository_version={repo_version}",
            },
            "rpm.modulemd_defaults": {
                "count": 45,
                "href": f"/pulp/api/v3/content/rpm/modulemd_defaults/?repository_version={repo_version}",
            },
            "rpm.modulemd": {
                "count": 426,
                "href": f"/pulp/api/v3/content/rpm/modulemds/?repository_version={repo_version}",
            },
            "rpm.advisory": {
                "count": 71,
                "href": f"/pulp/api/v3/content/rpm/advisories/?repository_version={repo_version}",
            },
        }

    monkeypatch.setattr(PulpClient, "get_latest_repo_present_content", func)


@pytest.fixture
def get_latest_repo_removed_content(monkeypatch):
    async def func(_, repo_version: str):
        return {
            "rpm.package": {
                "count": 5517,
                "href": f"/pulp/api/v3/content/rpm/packages/?repository_version={repo_version}",
            },
            "rpm.modulemd_defaults": {
                "count": 45,
                "href": f"/pulp/api/v3/content/rpm/modulemd_defaults/?repository_version={repo_version}",
            },
            "rpm.modulemd": {
                "count": 426,
                "href": f"/pulp/api/v3/content/rpm/modulemds/?repository_version={repo_version}",
            },
            "rpm.advisory": {
                "count": 71,
                "href": f"/pulp/api/v3/content/rpm/advisories/?repository_version={repo_version}",
            },
        }

    monkeypatch.setattr(PulpClient, "get_latest_repo_removed_content", func)


@pytest.fixture
def get_by_href(monkeypatch):
    async def func(*args):
        return {
            "count": 2,
            "next": None,
            "previous": None,
            "results": [
                {
                    "pulp_href": get_module_href(),
                    "pulp_created": "2023-01-13T07:56:45.740279Z",
                    "md5": None,
                    "sha1": None,
                    "sha224": None,
                    "sha256": "43e37ca53ab481ccfb2da47b05da3a14df2588ae3af41bc7ff787542dc1adbc8",
                    "sha384": None,
                    "sha512": None,
                    "artifact": get_artifact_href(),
                    "name": "container-tools",
                    "stream": "rhel8",
                    "version": "16735966051422586",
                    "static_context": None,
                    "context": "20125149",
                    "arch": "i686",
                    "artifacts": [],
                    "dependencies": [],
                    "packages": [],
                },
                {
                    "pulp_href": get_module_defaults_href(),
                    "pulp_created": "2022-11-10T20:27:26.472175Z",
                    "md5": None,
                    "sha1": None,
                    "sha224": None,
                    "sha256": "c3d3c76de2b8816ae07e0bdceb4d8c100b884117b34219f773198f9aec3400e2",
                    "sha384": None,
                    "sha512": None,
                    "artifact": get_artifact_href(),
                    "module": "container-tools",
                    "stream": "rhel8",
                    "profiles": ["common"],
                },
            ],
        }

    monkeypatch.setattr(PulpClient, "get_by_href", func)


@pytest.fixture
def upload_file(monkeypatch):
    async def func(*args, **kwargs):
        return get_artifact_href(), hashlib.sha256().hexdigest()

    monkeypatch.setattr(PulpClient, "upload_file", func)


@pytest.fixture
def create_module_by_payload(monkeypatch):
    async def func(*args, **kwargs):
        return get_module_href()

    monkeypatch.setattr(PulpClient, "create_module_by_payload", func)


@pytest.fixture
def create_module(monkeypatch):
    async def func(*args, **kwargs):
        return get_module_href(), hashlib.sha256().hexdigest()

    monkeypatch.setattr(PulpClient, "create_module", func)


@pytest.fixture
def create_build_rpm_repo(monkeypatch):
    async def func(*args, **kwargs):
        _, repo_name = args
        return (
            f"{settings.pulp_host}/pulp/content/builds/{repo_name}/",
            get_repo_href(),
        )

    monkeypatch.setattr(PulpClient, "create_build_rpm_repo", func)


@pytest.fixture
def modify_repository(monkeypatch):
    async def func(*args, **kwargs):
        return {
            "pulp_href": f"/pulp/api/v3/tasks/{uuid.uuid4()}/",
            "pulp_created": "2023-02-16T15:07:19.848386Z",
            "state": "completed",
            "name": "pulpcore.app.tasks.repository.add_and_remove",
            "logging_cid": "be6ca179753b4835b455efe7378e4cd4",
            "started_at": "2023-02-16T15:07:20.064012Z",
            "finished_at": "2023-02-16T15:07:42.201837Z",
            "error": None,
            "worker": f"/pulp/api/v3/workers/{uuid.uuid4()}/",
            "parent_task": None,
            "child_tasks": [],
            "task_group": None,
            "progress_reports": [
                {
                    "message": "Generating repository metadata",
                    "code": "publish.generating_metadata",
                    "state": "completed",
                    "total": 1,
                    "done": 1,
                    "suffix": None,
                }
            ],
            "created_resources": [
                f"/pulp/api/v3/publications/rpm/rpm/{uuid.uuid4()}/",
                "/pulp/api/v3/repositories/rpm/rpm/78982ebd-68e5-42ff-9620-67023f26f399/versions/1/",
            ],
            "reserved_resources_record": [
                "/pulp/api/v3/repositories/rpm/rpm/78982ebd-68e5-42ff-9620-67023f26f399/"
            ],
        }

    monkeypatch.setattr(PulpClient, "modify_repository", func)


@pytest.fixture
def create_rpm_publication(monkeypatch):
    async def func(*args, **kwargs):
        return {
            "pulp_href": "/pulp/api/v3/tasks/fd754c2e-3b6c-4d69-9417-6d7f5bdf1e28/",
            "pulp_created": "2023-02-16T15:06:52.836410Z",
            "state": "completed",
            "name": "pulp_file.app.tasks.publishing.publish",
            "logging_cid": "873348c8682944ad9cf2cc50745d5ba4",
            "started_at": "2023-02-16T15:06:53.072299Z",
            "finished_at": "2023-02-16T15:06:53.229928Z",
            "error": None,
            "worker": "/pulp/api/v3/workers/19ae1f30-d1cb-414c-9d42-29bda565e00d/",
            "parent_task": None,
            "child_tasks": [],
            "task_group": None,
            "progress_reports": [],
            "created_resources": [
                "/pulp/api/v3/publications/file/file/46bdd53c-3b99-4dae-8841-4fc71e551993/"
            ],
            "reserved_resources_record": [
                "shared:/pulp/api/v3/repositories/file/file/2ba385ce-9f41-4bbe-a09b-4524cfb32d9c/"
            ],
        }

    monkeypatch.setattr(PulpClient, "create_rpm_publication", func)


@pytest.fixture
def get_rpm_repo_by_params(monkeypatch):
    async def func(*args, **kwargs):
        return {
            "name": "almalinux-8-appstream-x86_64",
            "pulp_href": get_repo_href(),
        }

    monkeypatch.setattr(PulpClient, "get_rpm_repository_by_params", func)


@pytest.fixture
def create_log_repo(monkeypatch):
    async def func(*args, **kwargs):
        _, repo_name = args
        repo_prefix = kwargs["distro_path_start"]
        return (
            f"{settings.pulp_host}/pulp/content/{repo_prefix}/{repo_name}/",
            get_repo_href(),
        )

    monkeypatch.setattr(PulpClient, "create_log_repo", func)


@pytest.fixture
def get_repo_modules_yaml(
    monkeypatch,
    modular_build_payload: dict,
):
    async def func(*args, **kwargs):
        modules_yaml = modular_build_payload["tasks"][0]["modules_yaml"]
        _, repo_url = args
        repo_arch = re.search(
            r"-(?P<arch>\w+)-\d+-br/$",
            repo_url,
        )
        if not repo_arch:
            return modules_yaml
        repo_arch = repo_arch.groupdict()["arch"]
        _index = IndexWrapper.from_template(modules_yaml)
        for _module in _index.iter_modules():
            _module.arch = repo_arch
        return _index.render()

    monkeypatch.setattr(PulpClient, "get_repo_modules_yaml", func)


@pytest.fixture
def get_repo_modules(
    monkeypatch,
    modular_build_payload: dict,
):
    async def func(*args, **kwargs):
        return get_modules_href()

    monkeypatch.setattr(PulpClient, "get_repo_modules", func)


@pytest.fixture
def create_entity(monkeypatch):
    async def func(*args, **kwargs):
        _, artifact = args
        href = get_file_href()
        if artifact.type == "rpm":
            href = get_rpm_pkg_href()
        return href, hashlib.sha256().hexdigest(), artifact

    monkeypatch.setattr(PulpClient, "create_entity", func)


@pytest.fixture
def list_updateinfo_records(monkeypatch, pulp_updateinfos):
    async def func(*args, **kwargs):
        return pulp_updateinfos

    monkeypatch.setattr(PulpClient, "list_updateinfo_records", func)

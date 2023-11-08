import asyncio
import hashlib
import re
import uuid
from pathlib import Path

import pytest

from alws.config import settings
from alws.utils.modularity import IndexWrapper
from alws.utils.pulp_client import PulpClient
from tests.test_utils.pulp_utils import (
    get_artifact_href,
    get_distros_href,
    get_file_href,
    get_latest_repo_version,
    get_module_defaults_href,
    get_module_href,
    get_modules_href,
    get_repo_href,
    get_rpm_pkg_href,
)


@pytest.fixture(autouse=True)
def semaphore_patch(monkeypatch):
    monkeypatch.setattr(
        "alws.utils.pulp_client.PULP_SEMAPHORE",
        asyncio.Semaphore(5),
    )


@pytest.mark.anyio
@pytest.fixture(autouse=True)
async def disable_pulp_requests(monkeypatch):
    async def func(*args, **kwargs):
        return {}

    monkeypatch.setattr(PulpClient, 'request', func)


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
def create_multilib_module(monkeypatch, tmp_path: Path):
    async def func(*args, **kwargs):
        _, template, *_, arch = args
        template_file = tmp_path / f'modules.{arch}.yaml'
        result = get_module_href(), hashlib.sha256().hexdigest()
        if not template_file.exists():
            template_file.write_text(template)
            return result
        source_index = IndexWrapper.from_template(
            template_file.read_text(),
        )
        build_index = IndexWrapper.from_template(template)
        for build_module in build_index.iter_modules():
            source_module = source_index.get_module(
                build_module.name,
                build_module.stream,
            )
            for artifact in build_module.get_rpm_artifacts():
                source_module.raw_stream.add_rpm_artifact(artifact)
        template_file.write_text(source_index.render())
        return result

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
            "pulp_href": (
                "/pulp/api/v3/tasks/fd754c2e-3b6c-4d69-9417-6d7f5bdf1e28/"
            ),
            "pulp_created": "2023-02-16T15:06:52.836410Z",
            "state": "completed",
            "name": "pulp_file.app.tasks.publishing.publish",
            "logging_cid": "873348c8682944ad9cf2cc50745d5ba4",
            "started_at": "2023-02-16T15:06:53.072299Z",
            "finished_at": "2023-02-16T15:06:53.229928Z",
            "error": None,
            "worker": (
                "/pulp/api/v3/workers/19ae1f30-d1cb-414c-9d42-29bda565e00d/"
            ),
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


async def read_repo_modules(
    repo_url: str,
    module_template: str,
):
    repo_arch = re.search(
        r"-(?P<arch>\w+)-\d+-br/$",
        repo_url,
    )
    if not repo_arch:
        return module_template
    repo_arch = repo_arch.groupdict()["arch"]
    _index = IndexWrapper.from_template(module_template)
    for _module in _index.iter_modules():
        _module.arch = repo_arch
    return _index.render()


@pytest.fixture
def create_file_repository(monkeypatch):
    async def func(*args, **kwargs):
        _, repo_name, repo_prefix = args
        return (
            f"{settings.pulp_host}/pulp/content/{repo_prefix}/{repo_name}/",
            get_repo_href(),
        )

    monkeypatch.setattr(PulpClient, "create_file_repository", func)


@pytest.fixture
def get_repo_modules_yaml(
    monkeypatch,
    modular_build_payload: dict,
):
    async def func(*args, **kwargs):
        _, repo_url = args
        return await read_repo_modules(
            repo_url,
            modular_build_payload['tasks'][0]['modules_yaml'],
        )

    monkeypatch.setattr(PulpClient, "get_repo_modules_yaml", func)


@pytest.fixture
def get_repo_virt_modules_yaml(
    monkeypatch,
    virt_build_payload: dict,
):
    async def func(*args, **kwargs):
        _, repo_url = args
        return await read_repo_modules(
            repo_url,
            virt_build_payload['tasks'][0]['modules_yaml'],
        )

    monkeypatch.setattr(PulpClient, "get_repo_modules_yaml", func)


@pytest.fixture
def get_repo_ruby_modules_yaml(
    monkeypatch,
    ruby_build_payload: dict,
):
    async def func(*args, **kwargs):
        _, repo_url = args
        return await read_repo_modules(
            repo_url,
            ruby_build_payload['tasks'][0]['modules_yaml'],
        )

    monkeypatch.setattr(PulpClient, "get_repo_modules_yaml", func)


@pytest.fixture
def get_repo_subversion_modules_yaml(
    monkeypatch,
    subversion_build_payload: dict,
):
    async def func(*args, **kwargs):
        _, repo_url = args
        return await read_repo_modules(
            repo_url,
            subversion_build_payload['tasks'][0]['modules_yaml'],
        )

    monkeypatch.setattr(PulpClient, "get_repo_modules_yaml", func)


@pytest.fixture
def get_repo_llvm_modules_yaml(
    monkeypatch,
    llvm_build_payload: dict,
):
    async def func(*args, **kwargs):
        _, repo_url = args
        return await read_repo_modules(
            repo_url,
            llvm_build_payload['tasks'][0]['modules_yaml'],
        )

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


@pytest.fixture
def get_rpm_distros(monkeypatch):
    async def func(*args, **kwargs):
        return [
            {
                "pulp_href": get_distros_href(),
                "name": "rpm_distro_name",
            },
        ]

    monkeypatch.setattr(PulpClient, "get_rpm_distros", func)


@pytest.fixture
def delete_by_href(monkeypatch):
    async def func(*args, **kwargs):
        return {"pulp_href": f"/pulp/api/v3/tasks/{uuid.uuid4()}/"}

    monkeypatch.setattr(PulpClient, "delete_by_href", func)

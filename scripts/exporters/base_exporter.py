import asyncio
import json
import logging
import os
import re
import shutil
import sys
import threading
import urllib.parse
from datetime import datetime
from fnmatch import fnmatch
from pathlib import Path
from typing import (
    Awaitable,
    Callable,
    Dict,
    List,
    Literal,
    Optional,
    Tuple,
    Union,
)

import aiohttp
from plumbum import local
from sqlalchemy import select

sys.path.append(str(Path(__file__).parent.parent.parent))

from alws.config import settings
from alws.dependencies import get_async_db_session
from alws.models import Repository
from alws.utils.exporter import download_file, get_repodata_file_links
from alws.utils.pulp_client import get_pulp_client


def _task_duration(task: dict) -> Optional[float]:
    """
    Seconds a Pulp task spent running, or None if the task doesn't
    report when it started and finished.
    """
    try:
        started = datetime.fromisoformat(
            task["started_at"].replace("Z", "+00:00")
        )
        finished = datetime.fromisoformat(
            task["finished_at"].replace("Z", "+00:00")
        )
    except (KeyError, TypeError, ValueError, AttributeError):
        return None
    return (finished - started).total_seconds()


class ExportState:
    """
    Repository versions that were fully exported (Pulp export, metadata
    regeneration and repodata signing) to each export path.

    Pulp re-links every package of a repository on each export and
    createrepo_c runs on the whole directory afterwards, while most
    repositories don't change between exports. The state lets the
    exporter skip the repositories whose version hasn't changed since the
    last complete export, as long as they are still on the filesystem.
    """

    version = 1

    def __init__(self, path: Path, logger: logging.Logger):
        self.path = path
        self.logger = logger
        self._lock = threading.Lock()
        self._entries = self._load()

    def _load(self) -> dict:
        try:
            with open(self.path, "rt") as f:
                data = json.load(f)
        except FileNotFoundError:
            return {}
        except (OSError, ValueError):
            self.logger.warning(
                "Cannot read export state %s, starting from scratch",
                self.path,
                exc_info=True,
            )
            return {}
        if not isinstance(data, dict) or data.get("version") != self.version:
            return {}
        return data["entries"]

    def matches(
        self, export_path: str, repository_version: str, method: str
    ) -> bool:
        with self._lock:
            entry = self._entries.get(export_path)
        return bool(entry) and (
            entry.get("repository_version") == repository_version
            and entry.get("method") == method
        )

    def mark(self, export_path: str, repository_version: str, method: str):
        with self._lock:
            self._entries[export_path] = {
                "repository_version": repository_version,
                "method": method,
            }

    def save(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = self.path.with_name(f"{self.path.name}.tmp")
        with self._lock:
            entries = dict(self._entries)
        with open(tmp_path, "wt") as f:
            json.dump(
                {"version": self.version, "entries": entries},
                f,
                indent=1,
                sort_keys=True,
            )
        os.replace(tmp_path, self.path)


class BasePulpExporter:
    # Whether to check that the repodata downloaded from a distribution
    # describes the exported repository version, see _export_repository.
    verify_repodata_version = False
    # Whether to skip repositories recorded in ExportState whose version
    # hasn't changed and that are still present on the filesystem.
    skip_unchanged = False

    def __init__(
        self,
        repodata_cache_dir: str,
        logger_name: str = '',
        log_file_path: str = '/srv/exporter.log',
        verbose: bool = False,
        export_method: Literal['write', 'hardlink', 'symlink'] = 'hardlink',
        export_path: str = settings.pulp_export_path,
    ):
        self.pulp_client = get_pulp_client()
        self.export_method = export_method
        self.export_path = export_path
        self.createrepo_c = local["createrepo_c"]
        # Export paths whose downloaded repodata is known to describe
        # exactly the exported repository version
        self.repodata_matches_export: Dict[str, bool] = {}

        self.repodata_cache_dir = (
            Path(repodata_cache_dir).expanduser().absolute()
        )
        self.checksums_cache_dir = self.repodata_cache_dir.joinpath('checksums')
        for dir_path in (self.repodata_cache_dir, self.checksums_cache_dir):
            if dir_path.exists():
                continue
            dir_path.mkdir()

        self.logger = logging.getLogger(logger_name)
        Path(log_file_path).parent.mkdir(exist_ok=True)
        logging.basicConfig(
            format="%(asctime)s %(levelname)-8s %(message)s",
            level=logging.DEBUG if verbose else logging.INFO,
            datefmt="%Y-%m-%d %H:%M:%S",
            handlers=[
                logging.FileHandler(filename=log_file_path, mode="a"),
                logging.StreamHandler(stream=sys.stdout),
            ],
        )
        self.web_server_headers = {
            "Authorization": f"Bearer {settings.albs_jwt_token}",
        }

        self.export_state = ExportState(
            self.repodata_cache_dir.joinpath("export_state.json"),
            logger=self.logger,
        )
        # Export paths skipped in this run because they were already
        # exported at their current repository version
        self.unchanged_export_paths: set = set()
        # Repository version exported to each export path in this run
        self.exported_versions: Dict[str, str] = {}

    def is_unchanged(self, export_path: str) -> bool:
        return export_path in self.unchanged_export_paths

    def mark_exported(self, export_path: str):
        """
        Record that the export of the path is complete, so that it can be
        skipped next time if its repository version doesn't change.
        """
        repository_version = self.exported_versions.get(export_path)
        if repository_version is None:
            return
        self.export_state.mark(
            export_path, repository_version, self.export_method
        )

    @staticmethod
    def export_is_present(export_path: str) -> bool:
        """
        Whether the packages directory and the regenerated repodata of a
        previous export are still on the filesystem.
        """
        packages_dir = Path(export_path)
        repomd = packages_dir.parent / "repodata" / "repomd.xml"
        return packages_dir.is_dir() and repomd.is_file()

    def regenerate_repo_metadata(self, repo_path: str):
        partial_path = re.sub(
            str(settings.pulp_export_path), "", str(repo_path)
        ).strip("/")
        repodata_path = Path(repo_path, "repodata")
        repo_repodata_cache = self.repodata_cache_dir.joinpath(partial_path)
        cache_repodata_dir = repo_repodata_cache.joinpath("repodata")
        self.logger.info('Repodata cache dir: %s', cache_repodata_dir)
        args = [
            "--update",
            "--keep-all-metadata",
            "--cachedir",
            self.checksums_cache_dir,
        ]
        if repo_repodata_cache.exists():
            args.extend(["--update-md-path", cache_repodata_dir])
        args.append(repo_path)
        self.logger.info('Starting createrepo_c')
        _, stdout, _ = self.createrepo_c.run(args=args)
        self.logger.info(stdout)
        self.logger.info('createrepo_c is finished')
        # Cache newly generated repodata into folder for future re-use
        if not repo_repodata_cache.exists():
            repo_repodata_cache.mkdir(parents=True)
        else:
            # Remove previous repodata before copying new ones
            if cache_repodata_dir.exists():
                shutil.rmtree(cache_repodata_dir)

        shutil.copytree(repodata_path, cache_repodata_dir)

    def remove_packages_from_repo(
        self,
        repo_path: str,
        exclude_patterns: List[str],
    ):
        packages_dir = Path(repo_path)
        if not packages_dir.exists():
            self.logger.warning(
                'Packages directory does not exist: %s', repo_path,
            )
            return
        globs = [
            p + '*' if not p.endswith('*') else p
            for p in exclude_patterns
        ]
        removed_count = 0
        for rpm_file in packages_dir.rglob('*.rpm'):
            if any(fnmatch(rpm_file.name, g) for g in globs):
                self.logger.info('Removing package: %s', rpm_file)
                rpm_file.unlink()
                removed_count += 1
        self.logger.info(
            'Removed %d packages from %s', removed_count, repo_path,
        )

    async def create_filesystem_exporters(
        self,
        repository_ids: List[int],
        get_publications: bool = False,
    ):
        async def get_exporter_data(repository: Repository) -> Tuple[str, dict]:
            export_path = str(
                Path(self.export_path, repository.export_path, "Packages")
            )
            exporter_name = (
                f"{repository.name}-{repository.arch}-debug"
                if repository.debug
                else f"{repository.name}-{repository.arch}"
            )
            fs_exporter_href = (
                await self.pulp_client.create_filesystem_exporter(
                    exporter_name,
                    export_path,
                    export_method=self.export_method,
                )
            )

            repo_latest_version = (
                await self.pulp_client.get_repo_latest_version(
                    repository.pulp_href
                )
            )
            if not repo_latest_version:
                raise ValueError('cannot find latest repo version')
            repo_exporter_dict = {
                "repo_id": repository.id,
                "repo_url": repository.url,
                "repo_latest_version": repo_latest_version,
                "exporter_name": exporter_name,
                "export_path": export_path,
                "exporter_href": fs_exporter_href,
            }
            if get_publications:
                publications = await self.pulp_client.get_rpm_publications(
                    repository_version_href=repo_latest_version,
                    include_fields=["pulp_href"],
                )
                if publications:
                    publication_href = publications[0].get("pulp_href")
                    repo_exporter_dict["publication_href"] = publication_href
            return fs_exporter_href, repo_exporter_dict

        async with get_async_db_session() as session:
            query = select(Repository).where(Repository.id.in_(repository_ids))
            result = await session.execute(query)
            repositories = list(result.scalars().all())

        results = await asyncio.gather(
            *(get_exporter_data(repo) for repo in repositories)
        )

        return list(dict(results).values())

    async def download_repodata(self, repodata_path, repodata_url):
        file_links = await get_repodata_file_links(repodata_url)
        for link in file_links:
            file_name = Path(link).name
            if file_name.endswith('..'):
                continue
            self.logger.info("Downloading repodata from %s", link)
            await download_file(link, Path(repodata_path, file_name))

    async def _export_repository(self, exporter: dict) -> Optional[str]:
        self.logger.info(
            "Exporting repository using following data: %s",
            str(exporter),
        )
        export_path = exporter["export_path"]
        href = exporter["exporter_href"]
        repository_version = exporter["repo_latest_version"]
        self.exported_versions[export_path] = repository_version
        if self.skip_unchanged and self.export_state.matches(
            export_path, repository_version, self.export_method
        ):
            if self.export_is_present(export_path):
                self.logger.info(
                    "Repository %s is unchanged since the last export "
                    "(%s), skipping",
                    exporter["exporter_name"],
                    repository_version,
                )
                self.unchanged_export_paths.add(export_path)
                # The repodata on disk was generated from the exported
                # packages themselves, so it describes them exactly
                self.repodata_matches_export[export_path] = True
                return export_path
            self.logger.info(
                "Repository %s is missing on the filesystem, re-exporting",
                exporter["exporter_name"],
            )
        try:
            task = await self.pulp_client.export_to_filesystem(
                href, repository_version
            )
        except Exception:
            self.logger.exception(
                "Cannot export repository via %s",
                str(exporter),
            )
            return
        duration = _task_duration(task) if isinstance(task, dict) else None
        if duration is not None:
            self.logger.info(
                "Repository %s is exported by Pulp in %.1fs",
                exporter["exporter_name"],
                duration,
            )
        parent_dir = Path(export_path).parent
        if not parent_dir.exists():
            self.logger.info(
                "Repository %s directory is absent",
                exporter["exporter_name"],
            )
            return

        repodata_path = parent_dir.joinpath("repodata").absolute()
        repodata_url = urllib.parse.urljoin(exporter["repo_url"], "repodata/")
        if repodata_path.exists():
            shutil.rmtree(repodata_path)
        repodata_path.mkdir()
        self.logger.info('Downloading repodata from %s', repodata_url)
        # A distribution serves the publication of the latest repository
        # version that has one. That's the exported version only if it was
        # already published before the download and is still the latest one
        # after it; otherwise the repodata may describe another version.
        repodata_matches = (
            self.verify_repodata_version
            and await self._is_version_published(repository_version)
        )
        try:
            await self.download_repodata(repodata_path, repodata_url)
        except Exception as e:
            self.logger.exception("Cannot download repodata file: %s", str(e))
            repodata_matches = False
        if repodata_matches:
            repodata_matches = await self._is_latest_version(repository_version)
        self.repodata_matches_export[export_path] = repodata_matches

        return export_path

    async def _is_version_published(self, repository_version: str) -> bool:
        try:
            publications = await self.pulp_client.get_rpm_publications(
                repository_version_href=repository_version,
                include_fields=["pulp_href"],
            )
        except Exception:
            self.logger.warning(
                "Cannot get publications of %s",
                repository_version,
                exc_info=True,
            )
            return False
        return bool(publications)

    async def _is_latest_version(self, repository_version: str) -> bool:
        repository_href = repository_version.rsplit("versions/", 1)[0]
        try:
            latest_version = await self.pulp_client.get_repo_latest_version(
                repository_href
            )
        except Exception:
            self.logger.warning(
                "Cannot get the latest version of %s",
                repository_href,
                exc_info=True,
            )
            return False
        return latest_version == repository_version

    async def export_repositories(
        self,
        repo_ids: List[int],
        on_exported: Optional[Callable[[str], Awaitable[None]]] = None,
    ) -> List[str]:
        """
        Export the repositories and return their paths.

        on_exported is awaited with the path of each repository as soon
        as it's exported, while the others are still being exported.
        """
        exporters = await self.create_filesystem_exporters(repo_ids)

        async def export(exporter: dict) -> Optional[str]:
            path = await self._export_repository(exporter)
            if path and on_exported is not None:
                await on_exported(path)
            return path

        results = await asyncio.gather(*(export(e) for e in exporters))
        return [path for path in results if path]

    async def get_sign_keys(self):
        endpoint = "sign-keys/"
        return await self.make_request("GET", endpoint)

    async def get_sign_server_token(self) -> str:
        body = {
            'email': settings.sign_server_username,
            'password': settings.sign_server_password,
        }
        endpoint = 'token'
        method = 'POST'
        response = await self.make_request(
            method=method,
            endpoint=endpoint,
            body=body,
            send_to='sign_server',
        )
        return response['token']

    async def sign_repomd_xml(
        self,
        path_to_file: str,
        key_id: str,
        token: str,
        max_attempts: int = 5,
        initial_backoff: float = 2.0,
    ):
        endpoint = "sign"
        result = {"asc_content": None, "error": None}
        file_bytes = Path(path_to_file).read_bytes()
        backoff = initial_backoff
        for attempt in range(1, max_attempts + 1):
            err_msg = None
            try:
                response = await self.make_request(
                    "POST",
                    endpoint,
                    params={"keyid": key_id},
                    data={"file": file_bytes},
                    user_headers={"Authorization": f"Bearer {token}"},
                    send_to="sign_server",
                )
                if response:
                    result["asc_content"] = response
                    result["error"] = None
                    return result
                err_msg = "sign server returned empty response"
                result["error"] = err_msg
            except Exception as err:
                err_msg = err
                result["error"] = err

            if attempt == max_attempts:
                self.logger.error(
                    "Signing %s failed after %d attempts: %s",
                    path_to_file, attempt, err_msg,
                )
                break
            self.logger.warning(
                "Signing %s failed on attempt %d/%d: %s; retrying in %.1fs",
                path_to_file, attempt, max_attempts, err_msg, backoff,
            )
            await asyncio.sleep(backoff)
            backoff *= 2
        return result

    async def repomd_signer(self, repodata_path, key_id, token) -> bool:
        """
        Sign repomd.xml in the directory. Returns whether it's signed.
        """
        string_repodata_path = str(repodata_path)
        if key_id is None:
            self.logger.info(
                "Cannot sign repomd.xml in %s, missing GPG key",
                string_repodata_path,
            )
            return False

        file_path = os.path.join(repodata_path, "repomd.xml")
        result = await self.sign_repomd_xml(file_path, key_id, token)
        self.logger.info('PGP key id: %s', key_id)
        self.logger.info('sign-file result: %s', result)
        result_data = result.get("asc_content")
        if result_data is None:
            self.logger.error(
                "repomd.xml in %s is failed to sign:\n%s",
                string_repodata_path,
                result["error"],
            )
            return False

        repodata_path = os.path.join(repodata_path, "repomd.xml.asc")
        with open(repodata_path, "w") as file:
            file.writelines(result_data)
        self.logger.info("repomd.xml in %s is signed", string_repodata_path)
        return True

    async def make_request(
        self,
        method: str,
        endpoint: str,
        params: Optional[dict] = None,
        body: Optional[dict] = None,
        user_headers: Optional[dict] = None,
        data: Optional[list] = None,
        send_to: Literal['web_server', 'sign_server'] = 'web_server',
    ) -> Union[dict, str]:
        if send_to == 'web_server':
            headers = {**self.web_server_headers}
            full_url = urllib.parse.urljoin(settings.albs_api_url, endpoint)
        elif send_to == 'sign_server':
            headers = {}
            full_url = urllib.parse.urljoin(
                settings.sign_server_api_url,
                endpoint,
            )
        else:
            raise ValueError(
                "'send_to' param must be either 'web_server' or 'sign_server'"
            )

        if user_headers:
            headers.update(user_headers)

        async with aiohttp.ClientSession(
            headers=headers,
            raise_for_status=True,
            timeout=aiohttp.ClientTimeout(total=900),
        ) as session:
            async with session.request(
                method,
                full_url,
                json=body,
                params=params,
                data=data,
            ) as response:
                if response.headers['Content-Type'] == 'application/json':
                    return await response.json()
                return await response.text()

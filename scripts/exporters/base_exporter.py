import asyncio
import logging
import re
import shutil
import sys
import urllib.parse
from pathlib import Path
from typing import List, Literal, Optional, Tuple

from plumbum import local
from sqlalchemy import select

sys.path.append(str(Path(__file__).parent.parent.parent))

from alws.config import settings
from alws.dependencies import get_async_db_session
from alws.models import Repository
from alws.utils.exporter import download_file, get_repodata_file_links
from alws.utils.pulp_client import get_pulp_client


class BasePulpExporter:
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
        try:
            await self.pulp_client.export_to_filesystem(
                href, repository_version
            )
        except Exception:
            self.logger.exception(
                "Cannot export repository via %s",
                str(exporter),
            )
            return
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
        try:
            await self.download_repodata(repodata_path, repodata_url)
        except Exception as e:
            self.logger.exception("Cannot download repodata file: %s", str(e))

        return export_path

    async def export_repositories(self, repo_ids: List[int]) -> List[str]:
        exporters = await self.create_filesystem_exporters(repo_ids)
        results = await asyncio.gather(
            *(self._export_repository(e) for e in exporters)
        )
        return [path for path in results if path]

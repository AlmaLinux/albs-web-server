import argparse
import asyncio
import json
import logging
import os
import pwd
import re
import shutil
import sys
import tempfile
import typing
import urllib.parse
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from time import time

import aiohttp
import jmespath
import pgpy
import rpm
import sentry_sdk
import sqlalchemy

# Required for generating RSS
from feedgen.feed import FeedGenerator
from plumbum import local
from sqlalchemy.future import select
from sqlalchemy.orm import selectinload
from syncer import sync

sys.path.append(os.path.dirname(os.path.dirname(__file__)))


from alws import database, models
from alws.config import settings
from alws.constants import SignStatusEnum
from alws.utils.errata import (
    extract_errata_metadata,
    extract_errata_metadata_modern,
    find_metadata,
    generate_errata_page,
    iter_updateinfo,
    merge_errata_records,
    merge_errata_records_modern,
)
from alws.utils.exporter import download_file, get_repodata_file_links
from alws.utils.osv import export_errata_to_osv
from alws.utils.pulp_client import PulpClient

KNOWN_SUBKEYS_CONFIG = os.path.abspath(
    os.path.expanduser("~/config/known_subkeys.json")
)
LOG_DIR = Path.home() / "exporter_logs"
LOGGER_NAME = "packages-exporter"
LOG_FILE = LOG_DIR / f"{LOGGER_NAME}_{int(time())}.log"


def parse_args():
    parser = argparse.ArgumentParser(
        "packages_exporter",
        description=(
            "Packages exporter script. Exports repositories from Pulp and"
            " transfer them to the filesystem"
        ),
    )
    parser.add_argument(
        "-names",
        "--platform-names",
        type=str,
        nargs="+",
        required=False,
        help="List of platform names to export",
    )
    parser.add_argument(
        "-repos",
        "--repo-ids",
        type=int,
        nargs="+",
        required=False,
        help="List of repo ids to export",
    )
    parser.add_argument(
        "-a",
        "--arches",
        type=str,
        nargs="+",
        required=False,
        help="List of arches to export",
    )
    parser.add_argument(
        "-id",
        "--release-id",
        type=int,
        required=False,
        help="Extract repos by release_id",
    )
    parser.add_argument(
        "-c",
        "--cache-dir",
        type=str,
        default="~/.cache/pulp_exporter",
        required=False,
        help="Repodata cache directory",
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        default=False,
        required=False,
        help="Verbose output",
    )
    parser.add_argument(
        "-method",
        "--export-method",
        type=str,
        default="hardlink",
        required=False,
        help="Method of exporting (choices: write, hardlink, symlink)",
    )
    parser.add_argument(
        "-osv-dir",
        type=str,
        default=settings.pulp_export_path,
        required=False,
        help="The path to the directory where the OSV data will be generated",
    )
    return parser.parse_args()


def init_sentry():
    if not settings.sentry_dsn:
        return
    sentry_sdk.init(
        dsn=settings.sentry_dsn,
        traces_sample_rate=settings.sentry_traces_sample_rate,
        environment=settings.sentry_environment,
    )


class Exporter:
    def __init__(
        self,
        pulp_client: PulpClient,
        repodata_cache_dir: str,
        verbose: bool = False,
        export_method: str = "hardlink",
        osv_dir: str = settings.pulp_export_path,
    ):
        os.makedirs(LOG_DIR, exist_ok=True)
        logging.basicConfig(
            format="%(asctime)s %(levelname)-8s %(message)s",
            level=logging.DEBUG if verbose else logging.INFO,
            datefmt="%Y-%m-%d %H:%M:%S",
            handlers=[
                logging.FileHandler(filename=LOG_FILE, mode="a"),
                logging.StreamHandler(stream=sys.stdout),
            ],
        )

        self._temp_dir = tempfile.gettempdir()
        self.logger = logging.getLogger(LOGGER_NAME)
        self.pulp_client = pulp_client
        self.createrepo_c = local["createrepo_c"]
        self.web_server_headers = {
            "Authorization": f"Bearer {settings.albs_jwt_token}",
        }
        self.export_method = export_method
        self.osv_dir = osv_dir
        self.current_user = self.get_current_username()
        self.export_error_file = os.path.abspath(
            os.path.expanduser("~/export.err")
        )
        if os.path.exists(self.export_error_file):
            os.remove(self.export_error_file)
        self.repodata_cache_dir = os.path.abspath(
            os.path.expanduser(repodata_cache_dir)
        )
        self.checksums_cache_dir = os.path.join(
            self.repodata_cache_dir, "checksums"
        )
        if not os.path.exists(self.repodata_cache_dir):
            os.makedirs(self.repodata_cache_dir)
        if not os.path.exists(self.checksums_cache_dir):
            os.makedirs(self.checksums_cache_dir)
        self.known_subkeys = {}
        if os.path.exists(KNOWN_SUBKEYS_CONFIG):
            with open(KNOWN_SUBKEYS_CONFIG, "rt") as f:
                self.known_subkeys = json.load(f)

    @staticmethod
    def get_current_username():
        return pwd.getpwuid(os.getuid())[0]

    def process_osv_data(
        self,
        errata_cache: typing.List[typing.Dict[str, typing.Any]],
        platform: str,
    ):
        osv_distr_mapping = {
            "AlmaLinux-8": "AlmaLinux:8",
            "AlmaLinux-9": "AlmaLinux:9",
        }
        self.logger.debug("Generating OSV data")
        osv_target_dir = os.path.join(
            self.osv_dir,
            "osv",
            platform.lower().replace("-", ""),
        )
        if not os.path.exists(osv_target_dir):
            os.makedirs(osv_target_dir, exist_ok=True)
        export_errata_to_osv(
            errata_records=errata_cache,
            target_dir=osv_target_dir,
            ecosystem=osv_distr_mapping[platform],
        )
        self.logger.debug("OSV data are generated")

    async def make_request(
        self,
        method: str,
        endpoint: str,
        params: dict = None,
        body: dict = None,
        user_headers: dict = None,
        data: typing.Optional[list] = None,
        send_to: typing.Literal['web_server', 'sign_server'] = 'web_server',
    ):
        if send_to == 'web_server':
            headers = {**self.web_server_headers}
            full_url = urllib.parse.urljoin(settings.albs_api_url, endpoint)
        elif send_to == 'sign_server':
            headers = {}
            full_url = urllib.parse.urljoin(
                settings.sign_server_api_url, endpoint
            )
        else:
            raise ValueError(
                "send_to parameter must be either web_server or sign_server"
            )

        if user_headers:
            headers.update(user_headers)

        async with aiohttp.ClientSession(
            headers=headers, raise_for_status=True
        ) as session:
            async with session.request(
                method, full_url, json=body, params=params, data=data
            ) as response:
                if response.headers['Content-Type'] == 'application/json':
                    return await response.json()
                return await response.text()

    async def create_filesystem_exporters(
        self,
        repository_ids: typing.List[int],
        get_publications: bool = False,
    ):
        async def get_exporter_data(
            repository: models.Repository,
        ) -> typing.Tuple[str, dict]:
            export_path = str(
                Path(
                    settings.pulp_export_path,
                    repository.export_path,
                    "Packages",
                )
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

        async with database.Session() as db:
            query = select(models.Repository).where(
                models.Repository.id.in_(repository_ids)
            )
            result = await db.execute(query)
            repositories = list(result.scalars().all())

        results = await asyncio.gather(
            *(get_exporter_data(repo) for repo in repositories)
        )

        return list(dict(results).values())

    async def sign_repomd_xml(
        self, path_to_file: str, key_id: str, token: str
    ):
        endpoint = "sign"
        result = {"asc_content": None, "error": None}
        try:
            response = await self.make_request(
                "POST",
                endpoint,
                params={"keyid": key_id},
                data={"file": Path(path_to_file).read_bytes()},
                user_headers={"Authorization": f"Bearer {token}"},
                send_to="sign_server",
            )
            result["asc_content"] = response
        except Exception as err:
            result['error'] = err
        return result

    async def get_sign_keys(self):
        endpoint = "sign-keys/"
        return await self.make_request("GET", endpoint)

    # TODO: Use direct function call to alws.crud.errata_get_oval_xml
    async def get_oval_xml(
        self, platform_name: str, only_released: bool = False
    ):
        endpoint = "errata/get_oval_xml/"
        return await self.make_request(
            "GET",
            endpoint,
            params={
                "platform_name": platform_name,
                "only_released": str(only_released).lower(),
            },
        )

    async def generate_rss(self, platform, modern_cache):
        # Expect "AlmaLinux-9" here:
        dist_name = platform.replace('-', ' ')
        dist_version = platform.split('-')[-1]

        errata_data = modern_cache['data']
        sorted_errata_data = sorted(
            errata_data, key=lambda k: k['updated_date'], reverse=True
        )

        feed = FeedGenerator()
        feed.title(f'Errata Feed for {dist_name}')
        feed.link(href='https://errata.almalinux.org', rel='alternate')
        feed.description(f'Errata Feed for {dist_name}')
        feed.author(name='AlmaLinux Team', email='packager@almalinux.org')

        for erratum in sorted_errata_data[:500]:
            html_erratum_id = erratum['id'].replace(':', '-')
            title = f"[{erratum['id']}] {erratum['title']}"
            link = f"https://errata.almalinux.org/{dist_version}/{html_erratum_id}.html"
            pubDate = datetime.fromtimestamp(
                erratum['updated_date'], timezone.utc
            )
            content = f"<pre>{erratum['description']}</pre>"

            entry = feed.add_entry()
            entry.title(title)
            entry.link(href=link)
            entry.content(content, type='CDATA')
            entry.pubDate(pubDate)

        return feed.rss_str(pretty=True).decode('utf-8')

    async def download_repodata(self, repodata_path, repodata_url):
        file_links = await get_repodata_file_links(repodata_url)
        for link in file_links:
            file_name = os.path.basename(link)
            self.logger.info("Downloading repodata from %s", link)
            await download_file(link, os.path.join(repodata_path, file_name))

    async def _export_repository(self, exporter: dict) -> typing.Optional[str]:
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
        parent_dir = str(Path(export_path).parent)
        if not os.path.exists(parent_dir):
            self.logger.info(
                "Repository %s directory is absent",
                exporter["exporter_name"],
            )
            return

        repodata_path = os.path.abspath(os.path.join(parent_dir, "repodata"))
        repodata_url = urllib.parse.urljoin(exporter["repo_url"], "repodata/")
        if not os.path.exists(repodata_path):
            os.makedirs(repodata_path)
        else:
            shutil.rmtree(repodata_path)
            os.makedirs(repodata_path)
        self.logger.info('Downloading repodata from %s', repodata_url)
        try:
            await self.download_repodata(repodata_path, repodata_url)
        except Exception as e:
            self.logger.exception("Cannot download repodata file: %s", str(e))

        return export_path

    async def export_repositories(self, repo_ids: list) -> typing.List[str]:
        exporters = await self.create_filesystem_exporters(repo_ids)
        results = await asyncio.gather(
            *(self._export_repository(e) for e in exporters)
        )
        exported_paths = [i for i in results if i]
        return exported_paths

    async def repomd_signer(self, repodata_path, key_id, token):
        string_repodata_path = str(repodata_path)
        if key_id is None:
            self.logger.info(
                "Cannot sign repomd.xml in %s, missing GPG key",
                string_repodata_path,
            )
            return

        file_path = os.path.join(repodata_path, "repomd.xml")
        result = await self.sign_repomd_xml(file_path, key_id, token)
        self.logger.info('PGP key id: %s', key_id)
        result_data = result.get("asc_content")
        if result_data is None:
            self.logger.error(
                "repomd.xml in %s is failed to sign:\n%s",
                string_repodata_path,
                result["error"],
            )
            return

        repodata_path = os.path.join(repodata_path, "repomd.xml.asc")
        with open(repodata_path, "w") as file:
            file.writelines(result_data)
        self.logger.info("repomd.xml in %s is signed", string_repodata_path)

    def check_rpms_signature(self, repository_path: str, sign_keys: list):
        self.logger.info("Checking signature for %s repo", repository_path)
        key_ids_lower = [i.keyid.lower() for i in sign_keys]
        ts = rpm.TransactionSet()
        ts.setVSFlags(rpm._RPMVSF_NOSIGNATURES)

        def check(pkg_path: str) -> typing.Tuple[SignStatusEnum, str]:
            if not os.path.exists(pkg_path):
                return SignStatusEnum.READ_ERROR, ""

            with open(pkg_path, "rb") as fd:
                header = ts.hdrFromFdno(fd)
                signature = header[rpm.RPMTAG_SIGGPG]
                if not signature:
                    signature = header[rpm.RPMTAG_SIGPGP]
                if not signature:
                    return SignStatusEnum.NO_SIGNATURE, ""

                pgp_msg = pgpy.PGPMessage.from_blob(signature)
                for signature in pgp_msg.signatures:
                    sig = signature.signer.lower()
                    if sig in key_ids_lower:
                        return SignStatusEnum.SUCCESS, sig
                    for key_id in key_ids_lower:
                        sub_keys = self.known_subkeys.get(key_id, [])
                        if sig in sub_keys:
                            return SignStatusEnum.SUCCESS, sig

                return SignStatusEnum.WRONG_SIGNATURE, sig

        errored_packages = set()
        no_signature_packages = set()
        wrong_signature_packages = set()
        futures = {}

        with ThreadPoolExecutor(max_workers=10) as executor:
            for package in os.listdir(repository_path):
                package_path = os.path.join(repository_path, package)
                if not package_path.endswith(".rpm"):
                    self.logger.debug(
                        "Skipping non-RPM file or directory: %s",
                        package_path,
                    )
                    continue

                futures[executor.submit(check, package_path)] = package_path

            for future in as_completed(futures):
                package_path = futures[future]
                result, pkg_sig = future.result()
                if result == SignStatusEnum.READ_ERROR:
                    errored_packages.add(package_path)
                elif result == SignStatusEnum.NO_SIGNATURE:
                    no_signature_packages.add(package_path)
                elif result == SignStatusEnum.WRONG_SIGNATURE:
                    wrong_signature_packages.add(f"{package_path} {pkg_sig}")

        if (
            errored_packages
            or no_signature_packages
            or wrong_signature_packages
        ):
            if not os.path.exists(self.export_error_file):
                mode = "wt"
            else:
                mode = "at"
            lines = [f"Errors when checking packages in {repository_path}"]
            if errored_packages:
                lines.append("Packages that we cannot get information about:")
                lines.extend(list(errored_packages))
            if no_signature_packages:
                lines.append("Packages without signature:")
                lines.extend(list(no_signature_packages))
            if wrong_signature_packages:
                lines.append("Packages with wrong signature:")
                lines.extend(list(wrong_signature_packages))
            lines.append("\n")
            with open(self.export_error_file, mode=mode) as f:
                f.write("\n".join(lines))

        self.logger.info("Signature check is done")

    async def export_repos_from_pulp(
        self,
        platform_names: typing.List[str] = None,
        repo_ids: typing.List[int] = None,
        arches: typing.List[str] = None,
    ) -> typing.Tuple[typing.List[str], typing.Dict[int, str]]:
        platforms_dict = {}
        msg, msg_values = (
            "Start exporting packages for following platforms:\n%s",
            platform_names,
        )
        if repo_ids:
            msg, msg_values = (
                "Start exporting packages for following repositories:\n%s",
                repo_ids,
            )
        self.logger.info(msg, msg_values)
        where_conditions = models.Platform.is_reference.is_(False)
        if platform_names is not None:
            where_conditions = sqlalchemy.and_(
                models.Platform.name.in_(platform_names),
                models.Platform.is_reference.is_(False),
            )
        query = (
            select(models.Platform)
            .where(where_conditions)
            .options(
                selectinload(models.Platform.repos),
                selectinload(models.Platform.sign_keys),
            )
        )
        async with database.Session() as db:
            db_platforms = await db.execute(query)
        db_platforms = db_platforms.scalars().all()

        final_export_paths = []
        for db_platform in db_platforms:
            repo_ids_to_export = []
            platforms_dict[db_platform.id] = []
            for repo in db_platform.repos:
                if (repo_ids is not None and repo.id not in repo_ids) or (
                    repo.production is False
                ):
                    continue
                if arches is not None:
                    if repo.arch in arches:
                        platforms_dict[db_platform.id].append(repo.export_path)
                        repo_ids_to_export.append(repo.id)
                else:
                    platforms_dict[db_platform.id].append(repo.export_path)
                    repo_ids_to_export.append(repo.id)
            exported_paths = await self.export_repositories(
                list(set(repo_ids_to_export))
            )
            final_export_paths.extend(exported_paths)
            with ThreadPoolExecutor(max_workers=10) as executor:
                futures = {}
                for repo_path in exported_paths:
                    if not os.path.exists(repo_path):
                        self.logger.error("Path %s does not exist", repo_path)
                        continue
                    futures[
                        executor.submit(
                            self.check_rpms_signature,
                            repo_path,
                            db_platform.sign_keys,
                        )
                    ] = repo_path
                for future in as_completed(futures):
                    repo_path = futures[future]
                    self.logger.info(
                        '%s packages signatures are checked', repo_path
                    )
            self.logger.debug(
                "All repositories exported in following paths:\n%s",
                "\n".join((str(path) for path in exported_paths)),
            )
        return final_export_paths, platforms_dict

    async def export_repos_from_release(
        self,
        release_id: int,
    ) -> typing.Tuple[typing.List[str], int]:
        self.logger.info(
            "Start exporting packages from release id=%s", release_id
        )
        async with database.Session() as db:
            db_release = await db.execute(
                select(models.Release).where(models.Release.id == release_id)
            )
        db_release = db_release.scalars().first()

        repo_ids = jmespath.search(
            "packages[].repositories[].id", db_release.plan
        )
        repo_ids = list(set(repo_ids))
        exported_paths = await self.export_repositories(repo_ids)
        return exported_paths, db_release.platform_id

    def regenerate_repo_metadata(self, repo_path):
        partial_path = re.sub(
            str(settings.pulp_export_path), "", str(repo_path)
        ).strip("/")
        repodata_path = os.path.join(repo_path, "repodata")
        repo_repodata_cache = os.path.join(
            self.repodata_cache_dir, partial_path
        )
        cache_repodata_dir = os.path.join(repo_repodata_cache, "repodata")
        self.logger.info('Repodata cache dir: %s', cache_repodata_dir)
        args = [
            "--update",
            "--keep-all-metadata",
            "--cachedir",
            self.checksums_cache_dir,
        ]
        if os.path.exists(repo_repodata_cache):
            args.extend(["--update-md-path", cache_repodata_dir])
        args.append(repo_path)
        self.logger.info('Starting createrepo_c')
        _, stdout, _ = self.createrepo_c.run(args=args)
        self.logger.info(stdout)
        self.logger.info('createrepo_c is finished')
        # Cache newly generated repodata into folder for future re-use
        if not os.path.exists(repo_repodata_cache):
            os.makedirs(repo_repodata_cache)
        else:
            # Remove previous repodata before copying new ones
            if os.path.exists(cache_repodata_dir):
                shutil.rmtree(cache_repodata_dir)

        shutil.copytree(repodata_path, cache_repodata_dir)

    async def get_sign_server_token(self) -> str:
        body = {
            'email': settings.sign_server_username,
            'password': settings.sign_server_password,
        }
        endpoint = 'token'
        method = 'POST'
        response = await self.make_request(
            method=method, endpoint=endpoint, body=body, send_to='sign_server'
        )
        return response['token']


async def sign_repodata(
    exporter: Exporter,
    exported_paths: typing.List[str],
    platforms_dict: dict,
    db_sign_keys: list,
    key_id_by_platform: str = None,
):
    repodata_paths = []

    tasks = []
    token = await exporter.get_sign_server_token()

    for repo_path in exported_paths:
        path = Path(repo_path)
        parent_dir = path.parent
        repodata = parent_dir / "repodata"
        if not os.path.exists(repo_path):
            continue

        repodata_paths.append(repodata)

        key_id = key_id_by_platform or None
        for platform_id, platform_repos in platforms_dict.items():
            for repo_export_path in platform_repos:
                if repo_export_path in repo_path:
                    key_id = next(
                        (
                            sign_key["keyid"]
                            for sign_key in db_sign_keys
                            if sign_key["platform_id"] == platform_id
                        ),
                        None,
                    )
                    break
        exporter.logger.info('Key ID: %s', str(key_id))
        tasks.append(exporter.repomd_signer(repodata, key_id, token))

    await asyncio.gather(*tasks)


def extract_errata(repo_path: str):
    errata_records = []
    modern_errata_records = []
    if not os.path.exists(repo_path):
        logging.debug("%s is missing, skipping", repo_path)
        return errata_records, modern_errata_records

    path = Path(repo_path)
    parent_dir = path.parent
    repodata = parent_dir / "repodata"
    errata_file = find_metadata(str(repodata), "updateinfo")
    if not errata_file:
        logging.debug("updateinfo.xml is missing, skipping")
        return errata_records, modern_errata_records

    for record in iter_updateinfo(errata_file):
        errata_records.append(extract_errata_metadata(record))
        modern_errata_records.extend(
            extract_errata_metadata_modern(record)["data"]
        )
    return errata_records, modern_errata_records


def repo_post_processing(exporter: Exporter, repo_path: str):
    path = Path(repo_path)
    parent_dir = path.parent

    result = True
    try:
        exporter.regenerate_repo_metadata(parent_dir)
    except Exception as e:
        exporter.logger.exception("Post-processing failed: %s", str(e))
        result = False

    return result


def main():
    args = parse_args()
    init_sentry()

    platforms_dict = {}
    key_id_by_platform = None
    exported_paths = []
    pulp_client = PulpClient(
        settings.pulp_host,
        settings.pulp_user,
        settings.pulp_password,
    )
    exporter = Exporter(
        pulp_client,
        args.cache_dir,
        verbose=args.verbose,
        export_method=args.export_method,
        pulp_user=args.pulp_user,
        pulp_group=args.pulp_group,
        osv_dir=args.osv_dir,
    )

    db_sign_keys = sync(exporter.get_sign_keys())
    if args.release_id:
        release_id = args.release_id
        exported_paths, platform_id = sync(
            exporter.export_repos_from_release(release_id)
        )
        key_id_by_platform = next(
            (
                sign_key["keyid"]
                for sign_key in db_sign_keys
                if sign_key["platform_id"] == platform_id
            ),
            None,
        )

    if args.platform_names or args.repo_ids:
        platform_names = args.platform_names
        repo_ids = args.repo_ids
        exported_paths, platforms_dict = sync(
            exporter.export_repos_from_pulp(
                platform_names=platform_names,
                arches=args.arches,
                repo_ids=repo_ids,
            )
        )

    platform_errata_cache = {}
    platform_regex = re.compile(r"\/(almalinux|vault)\/9\/")

    with ThreadPoolExecutor(max_workers=4) as executor:
        post_processing_futures = {
            executor.submit(
                repo_post_processing, exporter, repo_path
            ): repo_path
            for repo_path in exported_paths
        }
        for future in as_completed(post_processing_futures):
            repo_path = post_processing_futures[future]
            result = future.result()
            if result:
                exporter.logger.info(
                    "%s post-processing is successful", repo_path
                )
            else:
                exporter.logger.error(
                    "%s post-processing has failed", repo_path
                )

    with ThreadPoolExecutor(max_workers=4) as executor:
        errata_futures = {
            executor.submit(extract_errata, exp_path): exp_path
            for exp_path in exported_paths
        }

        exporter.logger.debug("Starting errata extraction")
        for future in as_completed(errata_futures):
            repo_path = errata_futures[future]
            errata_records, modern_errata_records = future.result()
            if errata_records or modern_errata_records:
                exporter.logger.info(
                    "Extracted errata records from %s",
                    repo_path,
                )
                platform = "AlmaLinux-8"
                if platform_regex.search(repo_path):
                    platform = "AlmaLinux-9"
                if platform not in platform_errata_cache:
                    platform_errata_cache[platform] = {
                        "cache": [],
                        "modern_cache": {
                            "data": [],
                        },
                    }
                platform_cache = platform_errata_cache[platform]
                platform_cache["cache"] = merge_errata_records(
                    platform_cache["cache"], errata_records
                )
                platform_cache["modern_cache"] = merge_errata_records_modern(
                    platform_cache["modern_cache"],
                    {"data": modern_errata_records},
                )
        exporter.logger.debug("Errata extraction completed")

    sync(
        sign_repodata(
            exporter,
            exported_paths,
            platforms_dict,
            db_sign_keys,
            key_id_by_platform=key_id_by_platform,
        )
    )

    if args.platform_names:
        exporter.logger.info("Starting export errata.json and oval.xml")
        errata_export_base_path = None
        try:
            errata_export_base_path = os.path.join(
                settings.pulp_export_path, "errata"
            )
            if not os.path.exists(errata_export_base_path):
                os.mkdir(errata_export_base_path)
            for platform in args.platform_names:
                platform_path = os.path.join(errata_export_base_path, platform)
                if not os.path.exists(platform_path):
                    os.mkdir(platform_path)
                html_path = os.path.join(platform_path, "html")
                if not os.path.exists(html_path):
                    os.mkdir(html_path)
                errata_cache = platform_errata_cache[platform]["cache"]
                exporter.process_osv_data(errata_cache, platform)
                exporter.logger.debug("Generating HTML errata pages")
                for record in errata_cache:
                    generate_errata_page(record, html_path)
                exporter.logger.debug("HTML pages are generated")
                for item in errata_cache:
                    item["issued_date"] = {
                        "$date": int(item["issued_date"].timestamp() * 1000)
                    }
                    item["updated_date"] = {
                        "$date": int(item["updated_date"].timestamp() * 1000)
                    }
                exporter.logger.debug("Dumping errata data into JSON")
                with open(
                    os.path.join(platform_path, "errata.json"), "w"
                ) as fd:
                    json.dump(errata_cache, fd)
                with open(
                    os.path.join(platform_path, "errata.full.json"), "w"
                ) as fd:
                    json.dump(
                        platform_errata_cache[platform]["modern_cache"], fd
                    )
                exporter.logger.debug("JSON dump is done")
                exporter.logger.debug("Generating OVAL data")
                oval = sync(
                    # aiohttp is not able to send booleans in params.
                    # For this reason, we're passing only_released as a string,
                    # which in turn will be converted into boolean on backend
                    # side by fastapi/pydantic.
                    exporter.get_oval_xml(platform, only_released=True)
                )
                with open(os.path.join(platform_path, "oval.xml"), "w") as fd:
                    fd.write(oval)
                exporter.logger.debug("OVAL is generated")

                exporter.logger.debug(f"Generating RSS feed for {platform}")
                rss = sync(
                    exporter.generate_rss(
                        platform,
                        platform_errata_cache[platform]["modern_cache"],
                    )
                )
                with open(
                    os.path.join(platform_path, "errata.rss"), "w"
                ) as fd:
                    fd.write(rss)
                exporter.logger.debug(f"RSS generation for {platform} is done")
        except Exception:
            exporter.logger.exception("Error happened:\n")


if __name__ == "__main__":
    main()

import argparse
import asyncio
import hashlib
import json
import logging
import os
import pwd
import re
import sys
import threading
from concurrent.futures import Future, ThreadPoolExecutor, as_completed
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from time import time
from typing import Any, Dict, List, Literal, Optional, Tuple

import aiohttp
import createrepo_c as cr
import jmespath
import rpm
import sentry_sdk
import sqlalchemy
from fastapi_sqla import open_async_session

# Required for generating RSS
from feedgen.feed import FeedGenerator
from sqlalchemy.future import select
from sqlalchemy.orm import selectinload
from syncer import sync

sys.path.append(str(Path(__file__).parent.parent.parent))

from alws import models
from alws.config import settings
from alws.constants import SignStatusEnum
from alws.dependencies import get_async_db_key
from alws.utils.errata import (
    errata_page_file_name,
    errata_page_template_source,
    extract_errata_metadata,
    extract_errata_metadata_modern,
    find_metadata,
    generate_errata_page,
    iter_updateinfo,
    merge_errata_records,
    merge_errata_records_modern,
)
from alws.utils.fastapi_sqla_setup import setup_all
from alws.utils.osv import export_errata_to_osv
from scripts.exporters.base_exporter import BasePulpExporter

KNOWN_SUBKEYS_CONFIG = os.path.abspath(
    os.path.expanduser("~/config/known_subkeys.json")
)
# Sign key to fall back to when a platform has several keys attached and
# --sign-with wasn't passed explicitly.
DEFAULT_SIGN_KEY_ID = "DEE5C11CC2A1E572"
SIGNATURE_QUERY_FORMAT = (
    '%|SIGGPG?{%{SIGGPG:pgpsig}}:{%|SIGPGP?{%{SIGPGP:pgpsig}}:{}|}|'
)
SIGNATURE_KEY_ID_RE = re.compile(r'Key ID ([0-9a-f]+)$')
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
        "-sw",
        "--sign-with",
        type=str,
        required=False,
        help=(
            "GPG key id to use when signing repodata. Overrides the "
            "per-platform key lookup for every exported repository. "
            "When omitted, the key is taken from the platform; platforms "
            f"with several keys fall back to {DEFAULT_SIGN_KEY_ID}."
        ),
    )
    parser.add_argument(
        "--full-signature-check",
        action="store_true",
        default=False,
        required=False,
        help=(
            "Read the signature of every exported package instead of "
            "reusing the results of previous exports. The cache is "
            "refreshed anyway"
        ),
    )
    parser.add_argument(
        "-osv-dir",
        type=str,
        default=settings.pulp_export_path,
        required=False,
        help="The path to the directory where the OSV data will be generated",
    )
    parser.add_argument(
        "-f",
        "--force",
        action="store_true",
        default=False,
        required=False,
        help=(
            "Export every repository even if its Pulp version hasn't "
            "changed since the last complete export, and regenerate every "
            "HTML errata page. By default such repositories are skipped "
            "when they are still on the filesystem, and only the pages of "
            "changed errata are regenerated"
        ),
    )
    return parser.parse_args()


@contextmanager
def log_duration(logger: logging.Logger, step: str):
    start = time()
    logger.info("%s: started", step)
    try:
        yield
    finally:
        logger.info("%s: done in %.1fs", step, time() - start)


def init_sentry():
    if not settings.sentry_dsn:
        return
    sentry_sdk.init(
        dsn=settings.sentry_dsn,
        traces_sample_rate=settings.sentry_traces_sample_rate,
        environment=settings.sentry_environment,
    )


def read_package_signer(ts, pkg_path: str) -> Optional[str]:
    """
    Return the id of the key the package is signed with, the whole
    signature description if rpm can't tell the key, or None if the
    package isn't signed at all.
    """
    with open(pkg_path, "rb") as fd:
        header = ts.hdrFromFdno(fd)
    signature = header.format(SIGNATURE_QUERY_FORMAT)
    if not signature:
        return None
    match = SIGNATURE_KEY_ID_RE.search(signature)
    return match.group(1) if match else signature


def classify_signer(
    signer: Optional[str],
    key_ids_lower: List[str],
    known_subkeys: Dict[str, List[str]],
) -> Tuple[SignStatusEnum, str]:
    if signer is None:
        return SignStatusEnum.NO_SIGNATURE, ""
    if signer in key_ids_lower:
        return SignStatusEnum.SUCCESS, signer
    for key_id in key_ids_lower:
        if signer in known_subkeys.get(key_id, []):
            return SignStatusEnum.SUCCESS, signer
    return SignStatusEnum.WRONG_SIGNATURE, signer


def load_primary_checksums(repodata_dir: str) -> Dict[str, Tuple[str, int]]:
    """
    Map package file names to the checksum and size primary.xml
    records for them.
    """
    checksums = {}
    ambiguous = set()

    def add_package(pkg):
        file_name = os.path.basename(pkg.location_href)
        record = (f"{pkg.checksum_type}:{pkg.pkgId}", pkg.size_package)
        if checksums.setdefault(file_name, record) != record:
            # Same NVRA under different epochs: can't tell which one is
            # the file on disk
            ambiguous.add(file_name)

    primary_path = find_metadata(repodata_dir, "primary")
    if primary_path:
        cr.xml_parse_primary(primary_path, pkgcb=add_package, do_files=False)
    for file_name in ambiguous:
        del checksums[file_name]
    return checksums


# Tells a package missing from SignatureCache apart from a cached unsigned one
NOT_CACHED = object()


class SignatureCache:
    """
    Keys packages are signed with, by package checksum and size.

    Reading RPM headers is the slowest part of the signature check, while
    most packages stay the same between exports. A package rebuilt or
    re-signed under the same file name gets another checksum, so it's
    checked again. Only the signer is cached: whether it's allowed is
    decided anew on every export against the platform keys.
    """

    version = 1

    def __init__(
        self,
        path: Path,
        logger: logging.Logger,
        ignore_cached: bool = False,
    ):
        self.path = path
        self.logger = logger
        self.ignore_cached = ignore_cached
        self._lock = threading.Lock()
        self._cached = self._load()
        self._used = {}

    def _load(self) -> dict:
        try:
            with open(self.path, "rt") as f:
                data = json.load(f)
        except FileNotFoundError:
            return {}
        except (OSError, ValueError):
            self.logger.warning(
                "Cannot read signature cache %s, starting from scratch",
                self.path,
                exc_info=True,
            )
            return {}
        if not isinstance(data, dict) or data.get("version") != self.version:
            return {}
        return data["entries"]

    def get(self, key: str):
        with self._lock:
            if key in self._used:
                return self._used[key]
            if self.ignore_cached or key not in self._cached:
                return NOT_CACHED
            self._used[key] = self._cached[key]
            return self._used[key]

    def put(self, key: str, signer: Optional[str]):
        with self._lock:
            self._used[key] = signer

    def save(self, prune: bool):
        """
        Write the cache down. With prune, only the entries used since
        loading are kept, so packages removed from repositories go away.
        """
        entries = self._used if prune else {**self._cached, **self._used}
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = self.path.with_name(f"{self.path.name}.tmp")
        with open(tmp_path, "wt") as f:
            json.dump(
                {"version": self.version, "entries": entries},
                f,
                separators=(",", ":"),
            )
        os.replace(tmp_path, self.path)


class ErrataPageCache:
    """
    Fingerprints of the HTML errata pages written by the previous export.

    Rendering the pages of every erratum of a platform takes a minute,
    while only a few errata change between exports. A page is written
    again when its erratum or the template differ from the previous
    export, or when the page is missing.
    """

    version = 1

    def __init__(
        self,
        path: Path,
        logger: logging.Logger,
        ignore_cached: bool = False,
    ):
        self.path = path
        self.logger = logger
        self.ignore_cached = ignore_cached
        self._cached = self._load()
        self._used = {}

    def _load(self) -> dict:
        try:
            with open(self.path, "rt") as f:
                data = json.load(f)
        except FileNotFoundError:
            return {}
        except (OSError, ValueError):
            self.logger.warning(
                "Cannot read errata pages cache %s, starting from scratch",
                self.path,
                exc_info=True,
            )
            return {}
        if not isinstance(data, dict) or data.get("version") != self.version:
            return {}
        return data["entries"]

    @staticmethod
    def fingerprint(errata: dict) -> str:
        digest = hashlib.sha256(errata_page_template_source().encode())
        digest.update(
            json.dumps(errata, sort_keys=True, default=str).encode()
        )
        return digest.hexdigest()

    def is_current(self, page_path: str, fingerprint: str) -> bool:
        page_name = os.path.basename(page_path)
        return (
            not self.ignore_cached
            and self._cached.get(page_name) == fingerprint
            and os.path.isfile(page_path)
        )

    def put(self, page_path: str, fingerprint: str):
        self._used[os.path.basename(page_path)] = fingerprint

    def save(self):
        # The entries of errata that are gone are kept: errata are never
        # removed in practice, and a stale entry is harmless as a page
        # is only reused when it is present
        entries = {**self._cached, **self._used}
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = self.path.with_name(f"{self.path.name}.tmp")
        with open(tmp_path, "wt") as f:
            json.dump(
                {"version": self.version, "entries": entries},
                f,
                separators=(",", ":"),
            )
        os.replace(tmp_path, self.path)


class PackagesExporter(BasePulpExporter):
    verify_repodata_version = True

    def __init__(
        self,
        repodata_cache_dir: str,
        logger_name: str = '',
        log_file_path: Path = Path('/srv/exporter.log'),
        verbose: bool = False,
        export_method: Literal['write', 'hardlink', 'symlink'] = "hardlink",
        export_path: str = settings.pulp_export_path,
        osv_dir: str = settings.pulp_export_path,
        full_signature_check: bool = False,
        skip_unchanged: bool = True,
    ):
        super().__init__(
            repodata_cache_dir=repodata_cache_dir,
            logger_name=logger_name,
            log_file_path=log_file_path,
            verbose=verbose,
            export_method=export_method,
            export_path=export_path,
        )

        self.skip_unchanged = skip_unchanged
        self.osv_dir = osv_dir
        self.full_signature_check = full_signature_check
        self.current_user = self.get_current_username()
        self.export_error_file = os.path.abspath(
            os.path.expanduser("~/export.err")
        )
        if os.path.exists(self.export_error_file):
            os.remove(self.export_error_file)
        self.known_subkeys = {}
        if os.path.exists(KNOWN_SUBKEYS_CONFIG):
            with open(KNOWN_SUBKEYS_CONFIG, "rt") as f:
                self.known_subkeys = json.load(f)

    @staticmethod
    def get_current_username():
        return pwd.getpwuid(os.getuid())[0]

    def process_osv_data(
        self,
        errata_cache: List[Dict[str, Any]],
        platform: str,
    ):
        osv_distr_mapping = {
            "AlmaLinux-8": "AlmaLinux:8",
            "AlmaLinux-9": "AlmaLinux:9",
            "AlmaLinux-10": "AlmaLinux:10",
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

    # TODO: Use direct function call to alws.crud.errata_get_oval_xml
    async def get_oval_xml(
        self,
        platform_name: str,
        only_released: bool = False,
        max_attempts: int = 5,
        initial_backoff: float = 2.0,
    ):
        endpoint = "errata/get_new_oval_xml/"
        params = {
            "platform_name": platform_name,
            "only_released": str(only_released).lower(),
        }
        backoff = initial_backoff
        last_err = None
        for attempt in range(1, max_attempts + 1):
            try:
                return await self.make_request("GET", endpoint, params=params)
            except Exception as err:
                last_err = err
                if attempt == max_attempts:
                    self.logger.error(
                        "Fetching OVAL for %s failed after %d attempts: %s",
                        platform_name, attempt, err,
                    )
                    break
                self.logger.warning(
                    "Fetching OVAL for %s failed on attempt %d/%d: %s; retrying in %.1fs",
                    platform_name, attempt, max_attempts, err, backoff,
                )
                await asyncio.sleep(backoff)
                backoff *= 2
        raise last_err

    async def generate_rss(self, platform, modern_cache):
        # Expect "AlmaLinux-9" here:
        dist_name = platform.replace('-', ' ')
        dist_version = platform.split('-')[-1]

        errata_data = modern_cache['data']
        sorted_errata_data = sorted(
            errata_data,
            key=lambda k: k['updated_date'],
            reverse=True,
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
            pub_date = datetime.fromtimestamp(
                erratum['updated_date'],
                timezone.utc,
            )
            content = f"<pre>{erratum['description']}</pre>"

            entry = feed.add_entry()
            entry.title(title)
            entry.link(href=link)
            entry.content(content, type='CDATA')
            entry.pubDate(pub_date)

        return feed.rss_str(pretty=True).decode('utf-8')

    def check_rpms_signature(
        self,
        repository_path: str,
        sign_keys: list,
        signature_cache: Optional[SignatureCache] = None,
    ):
        self.logger.info("Checking signature for %s repo", repository_path)
        key_ids_lower = [i.keyid.lower() for i in sign_keys]
        ts = rpm.TransactionSet()
        ts.setVSFlags(rpm._RPMVSF_NOSIGNATURES | rpm._RPMVSF_NODIGESTS)

        # The checksums are as good as the repodata they come from, so they
        # are only used when it describes exactly the exported version.
        primary_checksums = {}
        if signature_cache is not None and self.repodata_matches_export.get(
            repository_path
        ):
            try:
                primary_checksums = load_primary_checksums(
                    str(Path(repository_path).parent / "repodata")
                )
            except Exception:
                self.logger.warning(
                    "Cannot read primary.xml of %s, checking every package",
                    repository_path,
                    exc_info=True,
                )

        errored_packages = set()
        signer_by_path = {}
        futures = {}
        cached_count = 0
        size_mismatches = 0

        with ThreadPoolExecutor(max_workers=10) as executor:
            for package in os.listdir(repository_path):
                package_path = os.path.join(repository_path, package)
                if not package_path.endswith(".rpm"):
                    self.logger.debug(
                        "Skipping non-RPM file or directory: %s",
                        package_path,
                    )
                    continue
                try:
                    size = os.stat(package_path).st_size
                except FileNotFoundError:
                    errored_packages.add(package_path)
                    continue

                cache_key = None
                if package in primary_checksums:
                    checksum, primary_size = primary_checksums[package]
                    if size == primary_size:
                        cache_key = f"{checksum}:{size}"
                    else:
                        size_mismatches += 1
                if cache_key:
                    signer = signature_cache.get(cache_key)
                    if signer is not NOT_CACHED:
                        signer_by_path[package_path] = signer
                        cached_count += 1
                        continue

                future = executor.submit(read_package_signer, ts, package_path)
                futures[future] = (package_path, cache_key)

            for future in as_completed(futures):
                package_path, cache_key = futures[future]
                signer = future.result()
                signer_by_path[package_path] = signer
                if cache_key:
                    signature_cache.put(cache_key, signer)

        if signature_cache is not None:
            self.logger.info(
                "%s: %d package signatures reused, %d read",
                repository_path,
                cached_count,
                len(futures),
            )
        if size_mismatches:
            self.logger.warning(
                "%s: %d packages differ in size from primary.xml",
                repository_path,
                size_mismatches,
            )

        no_signature_packages = set()
        wrong_signature_packages = set()
        for package_path, signer in signer_by_path.items():
            result, pkg_sig = classify_signer(
                signer, key_ids_lower, self.known_subkeys
            )
            if result == SignStatusEnum.NO_SIGNATURE:
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

    async def export_and_check_signatures(
        self,
        platform_name: str,
        repo_ids: List[int],
        sign_keys: list,
        partial: bool = False,
    ) -> List[str]:
        """
        Export the repositories of a platform and check the signatures of
        their packages, returning the exported paths.

        The packages of a repository are checked as soon as it's exported,
        while Pulp is still exporting the others. A repository unchanged
        since the last complete export holds the same packages that passed
        the check back then, so it's only checked again on a full
        signature check.
        """
        signature_cache = SignatureCache(
            self.repodata_cache_dir.joinpath(
                "signatures", f"{platform_name}.json"
            ),
            logger=self.logger,
            ignore_cached=self.full_signature_check,
        )
        skipped = []
        loop = asyncio.get_running_loop()

        with ThreadPoolExecutor(max_workers=10) as executor:

            async def check(repo_path: str):
                if not os.path.exists(repo_path):
                    self.logger.error("Path %s does not exist", repo_path)
                    return
                if (
                    self.is_unchanged(repo_path)
                    and not self.full_signature_check
                ):
                    self.logger.info(
                        "%s is unchanged, its packages signatures were "
                        "checked at the last export",
                        repo_path,
                    )
                    skipped.append(repo_path)
                    return
                await loop.run_in_executor(
                    executor,
                    self.check_rpms_signature,
                    repo_path,
                    sign_keys,
                    signature_cache,
                )
                self.logger.info(
                    '%s packages signatures are checked', repo_path
                )

            exported_paths = await self.export_repositories(
                repo_ids, on_exported=check
            )

        # The entries of the skipped repositories weren't used, so they
        # can only be pruned when every repository is checked
        try:
            signature_cache.save(prune=not partial and not skipped)
        except OSError:
            self.logger.warning(
                "Cannot save signature cache %s",
                signature_cache.path,
                exc_info=True,
            )
        return exported_paths

    async def export_repos_from_pulp(
        self,
        platform_names: Optional[List[str]] = None,
        repo_ids: Optional[List[int]] = None,
        arches: Optional[List[str]] = None,
    ) -> Tuple[List[str], Dict[int, str]]:
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
        async with open_async_session(key=get_async_db_key()) as db:
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
            exported_paths = await self.export_and_check_signatures(
                db_platform.name,
                list(set(repo_ids_to_export)),
                db_platform.sign_keys,
                # A partial export leaves the other repositories' entries
                # alone
                partial=repo_ids is not None or arches is not None,
            )
            final_export_paths.extend(exported_paths)
            self.logger.debug(
                "All repositories exported in following paths:\n%s",
                "\n".join((str(path) for path in exported_paths)),
            )
        return final_export_paths, platforms_dict

    async def export_repos_from_release(
        self,
        release_id: int,
    ) -> Tuple[List[str], int]:
        self.logger.info(
            "Start exporting packages from release id=%s",
            release_id,
        )
        async with open_async_session(key=get_async_db_key()) as db:
            db_release = await db.execute(
                select(models.Release).where(models.Release.id == release_id)
            )
        db_release = db_release.scalars().first()

        repo_ids = jmespath.search(
            "packages[].repositories[].id",
            db_release.plan,
        )
        repo_ids = list(set(repo_ids))
        exported_paths = await self.export_repositories(repo_ids)
        return exported_paths, db_release.platform_id


class AmbiguousSignKeyError(Exception):
    pass


def get_platform_sign_key_id(
    db_sign_keys: List[dict],
    platform_id: int,
    logger: Optional[logging.Logger] = None,
) -> Optional[str]:
    """
    Return the sign key id bound to the platform.

    A platform can have several sign keys attached (e.g. AlmaLinux-10 has
    both the main key and the EPEL AltArch one). In that case there is no
    way to guess which one the repodata must be signed with, so we fall
    back to DEFAULT_SIGN_KEY_ID if it's among them; otherwise the caller
    has to pick one explicitly via --sign-with.
    """
    matched_key_ids = [
        sign_key["keyid"]
        for sign_key in db_sign_keys
        # A key with no platforms attached has no list at all
        if platform_id in (sign_key.get("platform_ids") or [])
    ]
    if not matched_key_ids:
        return None
    if len(matched_key_ids) == 1:
        return matched_key_ids[0]
    if DEFAULT_SIGN_KEY_ID not in matched_key_ids:
        raise AmbiguousSignKeyError(
            f"Platform {platform_id} has several sign keys: "
            f"{', '.join(matched_key_ids)}, none of which is the default "
            f"{DEFAULT_SIGN_KEY_ID}. Pass the one to sign repodata with "
            "via --sign-with"
        )
    if logger:
        logger.warning(
            "Platform %s has several sign keys: %s. Falling back to the "
            "default %s; pass --sign-with to pick another one",
            platform_id,
            ", ".join(matched_key_ids),
            DEFAULT_SIGN_KEY_ID,
        )
    return DEFAULT_SIGN_KEY_ID


async def sign_repodata(
    exporter: PackagesExporter,
    exported_paths: List[str],
    platforms_dict: dict,
    db_sign_keys: list,
    key_id_by_platform: Optional[str] = None,
    override_key_id: Optional[str] = None,
) -> set:
    """
    Sign repomd.xml of the exported repositories. Returns the export
    paths whose repodata is signed, or has no key to be signed with.
    """
    tasks = {}
    signed_paths = set()
    token = await exporter.get_sign_server_token()

    for repo_path in exported_paths:
        path = Path(repo_path)
        parent_dir = path.parent
        repodata = parent_dir / "repodata"
        if not os.path.exists(repo_path):
            continue
        if (
            exporter.is_unchanged(repo_path)
            and (repodata / "repomd.xml.asc").is_file()
        ):
            exporter.logger.info(
                "repomd.xml in %s is unchanged and already signed", repodata
            )
            signed_paths.add(repo_path)
            continue

        key_id = override_key_id or key_id_by_platform or None
        if not override_key_id:
            for platform_id, platform_repos in platforms_dict.items():
                for repo_export_path in platform_repos:
                    if repo_export_path in repo_path:
                        key_id = get_platform_sign_key_id(
                            db_sign_keys,
                            platform_id,
                            logger=exporter.logger,
                        )
                        break
        exporter.logger.info('Key ID: %s', str(key_id))
        if key_id is None:
            # Nothing to sign with: the export is as complete as it gets
            signed_paths.add(repo_path)
        tasks[repo_path] = exporter.repomd_signer(repodata, key_id, token)

    results = await asyncio.gather(*tasks.values())
    for repo_path, signed in zip(tasks, results):
        if signed:
            signed_paths.add(repo_path)
    return signed_paths


def extract_errata(repo_path: str) -> Tuple[List[dict], List[dict]]:
    errata_records: List[dict] = []
    modern_errata_records: List[dict] = []
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


def repo_post_processing(exporter: PackagesExporter, repo_path: str) -> bool:
    if exporter.is_unchanged(repo_path):
        exporter.logger.info("%s is unchanged, keeping its repodata", repo_path)
        return True
    result = True
    try:
        exporter.regenerate_repo_metadata(str(Path(repo_path).parent))
    except Exception as e:
        exporter.logger.exception("Post-processing failed: %s", str(e))
        result = False
    return result


def generate_errata_pages(
    exporter: PackagesExporter,
    errata_cache: List[dict],
    html_path: str,
    platform: str,
) -> int:
    """
    Write the HTML pages of the errata that changed since the previous
    export and return their number.
    """
    page_cache = ErrataPageCache(
        exporter.repodata_cache_dir.joinpath(
            "errata_pages", f"{platform}.json"
        ),
        logger=exporter.logger,
        ignore_cached=not exporter.skip_unchanged,
    )
    generated = 0
    for record in errata_cache:
        # The page lists the packages by arch, and errata.json is written
        # from the same records after the pages: keep the order the same
        # whether the page is written or reused
        record["pkglist"]["packages"].sort(key=lambda x: x["arch"])
        page_path = os.path.join(html_path, errata_page_file_name(record))
        fingerprint = page_cache.fingerprint(record)
        if not page_cache.is_current(page_path, fingerprint):
            generate_errata_page(record, html_path)
            generated += 1
        page_cache.put(page_path, fingerprint)
    try:
        page_cache.save()
    except OSError:
        exporter.logger.warning(
            "Cannot save errata pages cache %s",
            page_cache.path,
            exc_info=True,
        )
    return generated


def start_oval_requests(
    exporter: PackagesExporter,
    platform_names: Optional[List[str]],
) -> Dict[str, Future]:
    """
    Request the OVAL document of each platform from the web server
    in the background.

    The web server composes it from the database, which takes a minute,
    and it doesn't depend on the export: let the web server work while
    the repositories are exported.
    """
    if not platform_names:
        return {}
    executor = ThreadPoolExecutor(
        max_workers=len(platform_names),
        thread_name_prefix="oval",
    )
    futures = {}
    for platform in platform_names:
        exporter.logger.info(
            "%s OVAL data: requested from the web server", platform
        )
        futures[platform] = executor.submit(
            asyncio.run,
            # aiohttp is not able to send booleans in params.
            # For this reason, we're passing only_released as a
            # string, which in turn will be converted into boolean
            # on backend side by fastapi/pydantic.
            exporter.get_oval_xml(platform, only_released=True),
        )
    # The threads finish the requests already submitted
    executor.shutdown(wait=False)
    return futures


def export_errata_and_oval(
    exporter: PackagesExporter,
    platform_errata_cache: dict,
    platform_names: Optional[List[str]] = None,
    oval_futures: Optional[Dict[str, Future]] = None,
):
    if not platform_names:
        return
    if oval_futures is None:
        oval_futures = start_oval_requests(exporter, platform_names)
    exporter.logger.info("Starting export errata.json and oval.xml")
    errata_export_base_path = None
    try:
        errata_export_base_path = os.path.join(
            settings.pulp_export_path,
            "errata",
        )
        if not os.path.exists(errata_export_base_path):
            os.mkdir(errata_export_base_path)
        for platform in platform_names:
            errata_cache = platform_errata_cache.get(platform, {}).get('cache')
            if not errata_cache:
                exporter.logger.debug('No errata cache for %s platform, skipping', platform)
                continue
            platform_path = os.path.join(errata_export_base_path, platform)
            if not os.path.exists(platform_path):
                os.mkdir(platform_path)
            html_path = os.path.join(platform_path, "html")
            if not os.path.exists(html_path):
                os.mkdir(html_path)
            with log_duration(exporter.logger, f"{platform} OSV data"):
                exporter.process_osv_data(errata_cache, platform)
            with log_duration(exporter.logger, f"{platform} HTML errata pages"):
                generated = generate_errata_pages(
                    exporter, errata_cache, html_path, platform
                )
                exporter.logger.info(
                    "%s HTML errata pages: %d of %d written, the others are "
                    "unchanged since the last export",
                    platform,
                    generated,
                    len(errata_cache),
                )
            for item in errata_cache:
                item["issued_date"] = {
                    "$date": int(item["issued_date"].timestamp() * 1000)
                }
                item["updated_date"] = {
                    "$date": int(item["updated_date"].timestamp() * 1000)
                }
            with log_duration(exporter.logger, f"{platform} errata JSON"):
                with open(
                    os.path.join(platform_path, "errata.json"), "w"
                ) as fd:
                    json.dump(errata_cache, fd)
                with open(
                    os.path.join(platform_path, "errata.full.json"), "w"
                ) as fd:
                    json.dump(
                        platform_errata_cache[platform]["modern_cache"],
                        fd,
                    )
            with log_duration(exporter.logger, f"{platform} RSS feed"):
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
            oval_future = oval_futures.get(platform)
            if oval_future is None:
                oval_future = start_oval_requests(exporter, [platform])[
                    platform
                ]
            wait_start = time()
            oval = oval_future.result()
            exporter.logger.info(
                "%s OVAL data: received from the web server after waiting "
                "%.1fs for it",
                platform,
                time() - wait_start,
            )
            with open(os.path.join(platform_path, "oval.xml"), "w") as fd:
                fd.write(oval)
    except Exception:
        exporter.logger.exception("Error happened:\n")


def extract_errata_from_exported_paths(
    exporter: PackagesExporter,
    exported_paths: List[str],
) -> dict:
    # Records of every repository of a platform, merged once at the end:
    # merging deep-copies the whole accumulated cache every time
    platform_records = {}
    with ThreadPoolExecutor(max_workers=4) as executor:
        errata_futures = {
            executor.submit(extract_errata, exp_path): exp_path
            for exp_path in exported_paths
        }

        exporter.logger.debug("Starting errata extraction")
        extracted = {}
        for future in as_completed(errata_futures):
            repo_path = errata_futures[future]
            extracted[repo_path] = future.result()
        exporter.logger.debug("Errata extraction completed")

    # The merged record of an erratum takes the collection name and the
    # module of the first repository it's found in: merge in a fixed
    # order so that the output doesn't change from one run to another
    for repo_path in sorted(extracted):
        errata_records, modern_errata_records = extracted[repo_path]
        if not errata_records and not modern_errata_records:
            continue
        exporter.logger.info("Extracted errata records from %s", repo_path)
        repo_match = re.search(r"/(almalinux|vault)/(\d+)/", repo_path)
        if repo_match:
            version = repo_match.group(2)
            platform = f"AlmaLinux-{version}"
        else:
            platform = "AlmaLinux-8"
        records, modern_records = platform_records.setdefault(
            platform, ([], [])
        )
        records.extend(errata_records)
        modern_records.extend(modern_errata_records)

    platform_errata_cache = {}
    for platform, (records, modern_records) in platform_records.items():
        platform_errata_cache[platform] = {
            "cache": merge_errata_records([], records),
            "modern_cache": merge_errata_records_modern(
                {"data": []}, {"data": modern_records}
            ),
        }
    return platform_errata_cache


def main():
    args = parse_args()
    init_sentry()
    sync(setup_all())

    platforms_dict = {}
    key_id_by_platform = None
    exported_paths = []
    exporter = PackagesExporter(
        repodata_cache_dir=args.cache_dir,
        logger_name=LOGGER_NAME,
        log_file_path=LOG_FILE,
        verbose=args.verbose,
        export_method=args.export_method,
        osv_dir=args.osv_dir,
        full_signature_check=args.full_signature_check,
        skip_unchanged=not args.force,
    )
    logger = exporter.logger

    db_sign_keys = sync(exporter.get_sign_keys())

    sign_key_id = None
    if args.sign_with:
        sign_key_id = next(
            (
                sign_key["keyid"]
                for sign_key in db_sign_keys
                if sign_key["keyid"] == args.sign_with
            ),
            None,
        )
        if not sign_key_id:
            raise Exception(
                "Aborting packages export, error was: couldn't retrieve "
                f"the '{args.sign_with}' sign key"
            )

    # The OVAL documents only depend on the database: let the web server
    # compose them during the export
    oval_futures = start_oval_requests(exporter, args.platform_names)

    if args.release_id:
        with log_duration(logger, "Export from Pulp and signature check"):
            exported_paths, platform_id = sync(
                exporter.export_repos_from_release(args.release_id)
            )
        if not sign_key_id:
            key_id_by_platform = get_platform_sign_key_id(
                db_sign_keys,
                platform_id,
                logger=exporter.logger,
            )

    if args.platform_names or args.repo_ids:
        with log_duration(logger, "Export from Pulp and signature check"):
            exported_paths, platforms_dict = sync(
                exporter.export_repos_from_pulp(
                    platform_names=args.platform_names,
                    arches=args.arches,
                    repo_ids=args.repo_ids,
                )
            )
        if not sign_key_id:
            # Fail fast, before the expensive post-processing, if any of the
            # exported platforms has an unresolvable sign key.
            for platform_id, platform_repos in platforms_dict.items():
                if platform_repos:
                    get_platform_sign_key_id(db_sign_keys, platform_id)

    unchanged_count = sum(
        exporter.is_unchanged(path) for path in exported_paths
    )
    logger.info(
        "%d repositories exported, %d of them unchanged since the last export",
        len(exported_paths),
        unchanged_count,
    )

    post_processed_paths = set()
    with log_duration(logger, "Repodata regeneration"):
        with ThreadPoolExecutor(max_workers=4) as executor:
            post_processing_futures = {
                executor.submit(
                    repo_post_processing,
                    exporter,
                    repo_path,
                ): repo_path
                for repo_path in exported_paths
            }
            for future in as_completed(post_processing_futures):
                repo_path = post_processing_futures[future]
                result = future.result()
                if result:
                    post_processed_paths.add(repo_path)
                    exporter.logger.info(
                        "%s post-processing is successful",
                        repo_path,
                    )
                else:
                    exporter.logger.error(
                        "%s post-processing has failed",
                        repo_path,
                    )

    with log_duration(logger, "Errata extraction"):
        platform_errata_cache = extract_errata_from_exported_paths(
            exporter=exporter,
            exported_paths=exported_paths,
        )

    with log_duration(logger, "Repodata signing"):
        signed_paths = sync(
            sign_repodata(
                exporter,
                exported_paths,
                platforms_dict,
                db_sign_keys,
                key_id_by_platform=key_id_by_platform,
                override_key_id=sign_key_id,
            )
        )

    # Only a repository that went through every step can be skipped next
    # time; a failed one is exported again
    for repo_path in post_processed_paths & signed_paths:
        exporter.mark_exported(repo_path)
    try:
        exporter.export_state.save()
    except OSError:
        logger.warning(
            "Cannot save export state %s",
            exporter.export_state.path,
            exc_info=True,
        )

    with log_duration(logger, "Errata, OSV, OVAL and RSS export"):
        export_errata_and_oval(
            exporter=exporter,
            platform_errata_cache=platform_errata_cache,
            platform_names=args.platform_names,
            oval_futures=oval_futures,
        )


if __name__ == "__main__":
    main()

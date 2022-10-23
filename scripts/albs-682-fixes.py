# Script: albs-682-pulp-fixes.py
# Authors:
# - Daniil Anfimov <danfimov@cloudlinux.com>
# - Javier Hernández <jhernandez@cloudlinux.com>
#
# Date: 19 Oct 2022
#
# Description: According to ALBS-682, we must:
# - Delete advisories from wrong platforms
# - Remove wrong package references
# - Remove the "Packages/" prefix seen in some filenames
#
# Usage: This script requires direct access to both Pulp
# and Build System DBs. For configuration issues ask in
# buildsys-internal channel on CloudLinux Slack.
# This script should be placed inside albs-web-server
# scripts folder as it uses modules inside the repo.
# REMEMBER: Do any backup before running the script in
# production just in case anything goes wrong.
#
import asyncio
import logging
import typing

import yaml
from sqlalchemy import select, delete
from sqlalchemy.orm import selectinload

import sys
import os
import re
import urllib.parse

sys.path.append(os.path.dirname(os.path.dirname(__file__)))

from alws.utils import pulp_client
from alws.database import PulpSession, SyncSession
from alws.config import settings
from alws.pulp_models import UpdateRecord, UpdatePackage
from alws.models import ErrataRecord, Platform, Repository


logging.basicConfig(
    format="%(asctime)s %(levelname)-8s %(message)s",
    level=logging.INFO,
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("albs-682-pulp-fixes.log"),
    ],
)

albs_errata_cache = {"AlmaLinux-8": [], "AlmaLinux-9": []}


async def prepare_albs_errata_cache():
    logging.info("Collecting errata records from ALBS DB")
    with SyncSession() as albs_db:
        albs_records = albs_db.execute(
            select(ErrataRecord).options(selectinload(ErrataRecord.platform))
        )
        for errata in albs_records.scalars().all():
            albs_errata_cache[errata.platform.name].append(errata.id)
    logging.info("Finished collecting errata records from ALBS DB")


async def prepare_albs_packages_cache(
    albs_record: ErrataRecord,
    pulp: pulp_client.PulpClient,
) -> typing.Dict[str, typing.Any]:
    albs_packages_cache = {}
    pulp_pkg_fields = [
        "name",
        "location_href",
        "arch",
        "version",
        "pulp_href",
        "pkgId",
        "release",
        "epoch",
        "rpm_sourcerpm",
        "sha256",
        "checksum_type",
    ]
    logging.info("Collecting pulp_packages for record %s", albs_record.id)
    for package in albs_record.packages:
        for albs_package in package.albs_packages:
            reboot_suggested = albs_package.errata_package.reboot_suggested
            pulp_pkg = await pulp.get_rpm_package(
                albs_package.get_pulp_href(),
                include_fields=pulp_pkg_fields,
            )
            pulp_pkg["reboot_suggested"] = reboot_suggested
            location_href = re.sub(r"^Packages/", "", pulp_pkg["location_href"])
            pulp_pkg["location_href"] = location_href
            albs_packages_cache[location_href] = pulp_pkg
    return albs_packages_cache


async def delete_unmatched_packages():
    pulp = pulp_client.PulpClient(
        settings.pulp_host, settings.pulp_user, settings.pulp_password
    )
    with PulpSession() as pulp_db, SyncSession() as albs_db, pulp_db.begin():
        albs_records = albs_db.execute(select(ErrataRecord))
        for albs_record in albs_records.scalars().all():
            # we shouldn't delete unmatched packages
            # for records that were generated in old BS
            if str(albs_record.updated_date) < "2022-06-27":
                continue
            logging.info("Start fixing pulp_packages for %s", albs_record.id)
            albs_packages_cache = await prepare_albs_packages_cache(
                albs_record,
                pulp,
            )
            pulp_records = pulp_db.execute(
                select(UpdateRecord).where(UpdateRecord.id == albs_record.id)
            )
            for record in pulp_records.scalars().all():
                for collection in record.collections:
                    for pulp_pkg in collection.packages:
                        if pulp_pkg.filename in albs_packages_cache:
                            continue
                        logging.info(
                            "Deleting package from %s: %s",
                            albs_record.id,
                            pulp_pkg.filename,
                        )
                        pulp_db.execute(
                            delete(UpdatePackage).where(
                                UpdatePackage.pulp_id == pulp_pkg.pulp_id
                            )
                        )
                        pulp_db.flush()
        pulp_db.commit()


async def delete_pulp_advisory(pulp_href_id):
    with PulpSession() as pulp_db, pulp_db.begin():
        pulp_record = (
            pulp_db.execute(
                select(UpdateRecord).where(UpdateRecord.content_ptr_id == pulp_href_id)
            )
            .scalars()
            .first()
        )
        for collection in pulp_record.collections:
            for pkg in collection.packages:
                pulp_db.delete(pkg)
            pulp_db.flush()
            pulp_db.delete(collection)
        pulp_db.flush()
        for ref in pulp_record.references:
            pulp_db.delete(ref)
        pulp_db.flush()
        pulp_db.delete(pulp_record)


async def delete_advisories_from_wrong_repos():
    logging.info("Deleting advisories from wrong repositories")
    pulp = pulp_client.PulpClient(
        settings.pulp_host,
        settings.pulp_user,
        settings.pulp_password,
    )

    async def get_repo_latest_version(
        repo: Repository,
    ) -> typing.Tuple[Repository, str]:
        repo_version = None
        try:
            repo_version = await pulp.get_repo_latest_version(repo.pulp_href)
        except Exception:
            logging.exception(
                "Cannot get latest repo_version for %s", f"{repo.name}-{repo.arch}"
            )
        return repo, repo_version

    async def list_errata_pulp(repo_href: str) -> dict:
        endpoint = "pulp/api/v3/content/rpm/advisories/"
        params = {
            "fields": "id,pulp_href",
            "repository_version": repo_href,
        }
        result = {}

        def update_result(response: typing.List[dict]):
            for rec in response:
                _id = rec["id"]
                result[_id] = rec["pulp_href"]

        response = await pulp.request("GET", endpoint, params=params)
        update_result(response.get("results", []))
        next_page = response.get("next")
        if not next_page:
            return result
        while True:
            if (
                "limit" in next_page
                and re.search(r"limit=(\d+)", next_page).groups()[0] == "100"
            ):
                next_page = next_page.replace("limit=100", "limit=1000")
            parsed_url = urllib.parse.urlsplit(next_page)
            path = parsed_url.path + "?" + parsed_url.query
            response = await pulp.get_by_href(path)
            update_result(response.get("results", []))
            next_page = response.get("next")
            if not next_page:
                break
        return result

    with SyncSession() as albs_db:
        db_platforms: typing.List[Platform] = (
            albs_db.execute(
                select(Platform)
                .where(Platform.is_reference.is_(False))
                .options(selectinload(Platform.repos))
            )
            .scalars()
            .all()
        )
        for db_platform in db_platforms:
            if db_platform.distr_version == "8":
                platform = "AlmaLinux-8"
                opposite_platform = "AlmaLinux-9"
            else:
                platform = "AlmaLinux-9"
                opposite_platform = "AlmaLinux-8"

            latest_repo_versions = await asyncio.gather(
                *(get_repo_latest_version(repo) for repo in db_platform.repos if repo)
            )
            for repo, repo_href in latest_repo_versions:
                if not repo or not repo_href:
                    continue
                repo_errata = await list_errata_pulp(repo_href)

                for errata_id, errata_href in repo_errata.items():
                    if (
                        errata_id not in albs_errata_cache[platform]
                        and errata_id in albs_errata_cache[opposite_platform]
                    ):
                        logging.info(
                            "Removing %s as it doesn't belong to %s but %s",
                            f"{errata_id}:{errata_href}",
                            platform,
                            opposite_platform,
                        )
                        # pulp_href looks like "/pulp/api/v3/content/rpm/advisories/de779b2a-d4e3-4884-93a5-f91fcf37576c/"
                        # and we only need the id
                        pulp_href_id = errata_href.split("/")[-2]
                        await delete_pulp_advisory(pulp_href_id)


async def delete_wrong_packages():
    logging.info("Deleting wrong packages from advisories")
    with PulpSession() as pulp_db, SyncSession() as albs_db, pulp_db.begin():
        albs_records = albs_db.execute(select(ErrataRecord))
        for albs_record in albs_records.scalars().all():
            distr_version = albs_record.platform.distr_version
            # It is safe to make it this way since a release string
            # won't have git refs that include the character "l" :P
            albs_record_release = "el" + str(distr_version)

            pulp_records = (
                pulp_db.execute(
                    select(UpdateRecord).where(UpdateRecord.id == albs_record.id)
                )
                .scalars()
                .all()
            )

            for pulp_record in pulp_records:
                if pulp_record is None:
                    continue
                for collection in pulp_record.collections:
                    for pkg in collection.packages:
                        if albs_record_release not in pkg.release:
                            logging.info(
                                f"Deleting {pkg.filename} from {pulp_record.id} "
                                f"because release '{pkg.release}' doesn't match "
                                f"albs_record_release '{albs_record_release}'"
                            )
                            pulp_db.delete(pkg)
        pulp_db.commit()


async def delete_packages_prefix():
    logging.info("Deleting 'Packages/' prefix from filenames")
    with PulpSession() as pulp_db, pulp_db.begin():
        advisory_pkgs = pulp_db.execute(select(UpdatePackage)).scalars().all()

        for pkg in advisory_pkgs:
            if pkg.filename.startswith("Packages/"):
                pkg.filename = pkg.filename.replace("Packages/", "")

        pulp_db.commit()


async def update_pulp_repo(repo, pulp):
    repo_name = repo["name"] + "-" + repo["arch"]
    logging.info("Updating for repo %s is started", repo_name)
    pulp_repo = await pulp.get_rpm_repository(repo_name)
    if not pulp_repo:
        return
    await pulp.create_rpm_publication(pulp_repo["pulp_href"])
    logging.info("Updating for repo %s is done", repo_name)


async def update_pulp_repos():
    logging.info("Executing publications for pulp repositories")
    pulp = pulp_client.PulpClient(
        settings.pulp_host, settings.pulp_user, settings.pulp_password
    )
    platforms = yaml.safe_load(open("reference_data/platforms.yaml", "r").read())
    tasks = []
    for platform in platforms:
        for repo in platform["repositories"]:
            if not repo.get("production"):
                continue
            tasks.append(update_pulp_repo(repo, pulp))
    await asyncio.gather(*tasks)


async def main():
    pulp_client.PULP_SEMAPHORE = asyncio.Semaphore(10)

    await prepare_albs_errata_cache()

    await delete_advisories_from_wrong_repos()

    await delete_wrong_packages()
    await delete_packages_prefix()

    await delete_unmatched_packages()

    # We need to re-publicate the repos
    # after the modifications we just made
    await update_pulp_repos()


if __name__ == "__main__":
    asyncio.run(main())

import asyncio
import logging
import re
import typing

import yaml
from sqlalchemy import select
import createrepo_c as cr

import sys
import os

sys.path.append(os.path.dirname(os.path.dirname(__file__)))

from alws.utils import pulp_client
from alws.database import PulpSession, SyncSession
from alws.config import settings
from alws.constants import ErrataPackageStatus
from alws.pulp_models import UpdateRecord, UpdatePackage
from alws.models import (
    ErrataRecord,
)


logging.basicConfig(
    format="%(asctime)s %(levelname)-8s %(message)s",
    level=logging.INFO,
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("errata_fix_wrong_packages.log"),
    ],
)


async def update_pulp_repo(repo, pulp):
    repo_name = repo["name"] + "-" + repo["arch"]
    logging.info("Updating for repo %s is started", repo_name)
    pulp_repo = await pulp.get_rpm_repository(repo_name)
    if not pulp_repo:
        return
    await pulp.create_rpm_publication(pulp_repo["pulp_href"])
    logging.info(f"Updating for repo {repo} is done")


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
            if albs_package.status != ErrataPackageStatus.released:
                continue
            reboot_suggested = albs_package.errata_package.reboot_suggested
            try:
                pulp_pkg = await pulp.get_rpm_package(
                    albs_package.get_pulp_href(),
                    include_fields=pulp_pkg_fields,
                )
            except Exception:
                logging.exception(
                    'Cannot get pulp_pkg by %s',
                    albs_package.get_pulp_href(),
                )
                continue
            pulp_pkg["reboot_suggested"] = reboot_suggested
            location_href = re.sub(
                r"^Packages/", "", pulp_pkg["location_href"]
            )
            pulp_pkg["location_href"] = location_href
            albs_packages_cache[location_href] = pulp_pkg
    return albs_packages_cache


async def fix_errata_pulp(only_check: bool = False):
    logging.info("Update pulp db is started")
    pulp = pulp_client.PulpClient(
        settings.pulp_host, settings.pulp_user, settings.pulp_password
    )
    with PulpSession() as pulp_db, SyncSession() as albs_db, pulp_db.begin():
        albs_records = albs_db.execute(
            select(ErrataRecord)
            # date when errata and oval were merged
            .where(ErrataRecord.issued_date >= '2022-06-27')
        )
        for albs_record in albs_records.scalars().all():
            logging.info(
                "Start fixing pulp_packages for %s", albs_record.id
            )
            albs_packages_cache = await prepare_albs_packages_cache(
                albs_record,
                pulp,
            )
            pulp_records = pulp_db.execute(
                select(UpdateRecord)
                .where(UpdateRecord.id == albs_record.id)
            )
            for record in pulp_records.scalars().all():
                collection = record.collections[0]
                collection_arch = re.search(
                    r"i686|x86_64|aarch64|ppc64le|s390x",
                    collection.name,
                ).group()
                for pulp_pkg in collection.packages:
                    if pulp_pkg.filename in albs_packages_cache:
                        continue
                    logging.info(
                        "Package %s can be deleted from %s" if only_check
                        else "Deleting package from %s: %s",
                        albs_record.id,
                        pulp_pkg.filename,
                    )
                    if only_check:
                        continue
                    pulp_db.delete(pulp_pkg)
                existent_update_pkgs = {
                    pkg.filename
                    for pkg in collection.packages
                }
                for albs_pkg in albs_packages_cache.values():
                    if (
                        albs_pkg["arch"] not in (collection_arch, "noarch")
                        or albs_pkg["location_href"] in existent_update_pkgs
                    ):
                        continue
                    if (
                        albs_pkg["sha256"] is None
                        and albs_pkg["checksum_type"] == "sha256"
                    ):
                        logging.warning(
                            "sha256 sum is missing for %s using pkgId instead",
                            albs_pkg["location_href"],
                        )
                        albs_pkg["sha256"] = albs_pkg["pkgId"]
                    if only_check:
                        logging.info(
                            "Package can be added %s for errata %s",
                            albs_pkg["location_href"],
                            albs_record.id,
                        )
                        continue
                    collection.packages.append(
                        UpdatePackage(
                            name=albs_pkg["name"],
                            filename=albs_pkg["location_href"],
                            arch=albs_pkg["arch"],
                            version=albs_pkg["version"],
                            release=albs_pkg["release"],
                            epoch=str(albs_pkg["epoch"]),
                            reboot_suggested=albs_pkg["reboot_suggested"],
                            src=albs_pkg["rpm_sourcerpm"],
                            sum=albs_pkg["sha256"],
                            sum_type=cr.checksum_type("sha256"),
                        )
                    )
                    logging.info(
                        "Added package %s for errata %s",
                        albs_pkg["location_href"],
                        albs_record.id,
                    )
            logging.info("pulp_packages for %s is fixed", albs_record.id)
        if only_check:
            return
        pulp_db.commit()
    logging.info("Executing publications for pulp repositories")
    platforms = yaml.safe_load(
        open("reference_data/platforms.yaml", "r").read()
    )
    tasks = []
    for platform in platforms:
        for repo in platform["repositories"]:
            if not repo.get("production"):
                continue
            tasks.append(update_pulp_repo(repo, pulp))
    await asyncio.gather(*tasks)


async def main():
    pulp_client.PULP_SEMAPHORE = asyncio.Semaphore(10)
    await fix_errata_pulp(only_check=True)


if __name__ == "__main__":
    asyncio.run(main())

# script: albs-1037_fix_missing_errata_pkgs.py
# author: Javier Hernández <jhernandez@cloudlinux.com>
#
# Look for missing x86_64 or i686 errata packages in Pulp's update records.
# Since we use ALBS to release erratas, we can trust the data coming from
# our ErrataToALBSPackages table.
# If the package's status is 'released', the package should also be present in
# Pulp update record's collection.
#
import argparse
import asyncio
import datetime
import logging
import os
import re
import sys
import createrepo_c as cr

from collections import defaultdict
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from alws.database import PulpSession, SyncSession

from alws.constants import ErrataPackageStatus
from alws.models import (
    ErrataRecord,
    ErrataPackage,
    ErrataToALBSPackage,
)

from alws.config import settings
from alws.utils import pulp_client
from alws.pulp_models import (
    CoreRepository,
    UpdateRecord,
    UpdateCollection,
    UpdatePackage,
)

sys.path.append(os.path.dirname(os.path.dirname(__file__)))


logging.basicConfig(
    format="%(asctime)s %(levelname)-8s %(message)s",
    level=logging.INFO,
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("albs-1037_fix_missing_errata_pkgs.log"),
    ],
)


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument('--perform-updates', action='store_true', default=False)
    return parser.parse_args()


def get_released_intel_errata_to_albs_packages():
    # In addition to i686 and x86_64, we add noarch packages as they are
    # also part of pulp's UpdateCollection.packages. This way we can easily find
    # Pulp's missing pkgs.
    output_dict = defaultdict(list)
    with SyncSession() as db, db.begin():
        for err_pkg, err_to_albs_pkg in db.query(
            ErrataPackage,
            ErrataToALBSPackage).options(
                selectinload(ErrataToALBSPackage.errata_package)
            ).filter(
                ErrataPackage.id == ErrataToALBSPackage.errata_package_id,
                ErrataToALBSPackage.arch.in_(['i686', 'x86_64', 'noarch']),
                ErrataToALBSPackage.status == ErrataPackageStatus.released,
            ).all():
            output_dict[err_pkg.errata_record_id].append(err_to_albs_pkg)
        return output_dict


async def get_intel_update_collections(update_record_id: str):
    with PulpSession() as pulp_db, pulp_db.begin():
        subquery = (
            select(UpdateRecord.content_ptr_id).where(
                UpdateRecord.id == update_record_id
            ).scalar_subquery()
        )

        query = select(UpdateCollection).distinct(UpdateCollection.name).where(
            UpdateCollection.name.like('%for-x86_64%'),
            UpdateCollection.update_record_id.in_(subquery)
        ).options(
            selectinload(UpdateCollection.packages)
        ).order_by(
            UpdateCollection.name,
            UpdateCollection.pulp_last_updated.desc()
        )

        collections = pulp_db.execute(query).scalars().all()

        return collections


def get_real_repo_name(name):
    repo_info = re.search(
        r"^(?P<distr>almalinux)-(?P<distr_ver>\d)-for-(?P<arch>i686|x86_64|aarch64|ppc64le|s390x)-(?P<repo_name>\w+)-.+",
        name
    )
    if not repo_info:
        logging.warning(
            "Couldn't get repo name '%s'",
            name,
        )
        return
    repo_info = repo_info.groupdict()
    repo_name = "-".join(
        [
            repo_info["distr"],
            repo_info["distr_ver"],
            repo_info["repo_name"],
            repo_info["arch"],
        ]
    )
    return repo_name


def get_pulp_repo_by_name(name):
    with PulpSession() as pulp_db, pulp_db.begin():
        return pulp_db.execute(
            select(CoreRepository.pulp_id).where(
                CoreRepository.name == name
            )
        ).scalars().first()


async def add_missing_pkgs_to_pulp_update_collections(
    pulp,
    missing_pkgs,
    pulp_intel_collections,
    perform_updates
):
    repos_for_publication = set()

    for collection in pulp_intel_collections:
        repo_name = get_real_repo_name(collection.name)
        if not repo_name:
            continue
        repo_pulp_id = get_pulp_repo_by_name(repo_name)
        repo_href = f"/pulp/api/v3/repositories/rpm/rpm/{repo_pulp_id}/"

        for missing_pkg in missing_pkgs:
            search_params = {
                'name': missing_pkg.name,
                'version': missing_pkg.version,
                'arch': missing_pkg.arch
            }
            # Check if pkg belongs to collection. This is, check if the package exists
            # in collection's repository. If not, then there's no need to fix it.
            pulp_pkgs = await pulp.get_rpm_repository_packages(repo_href, **search_params)
            if not pulp_pkgs:
                continue
            # Pulp's API returns most recent version first
            pulp_pkg = pulp_pkgs[0]

            logging.info(f"Adding {pulp_pkg['name']}-{pulp_pkg['version']}.{pulp_pkg['arch']} into {repo_name}")
            with PulpSession() as pulp_db, pulp_db.begin():
                pulp_record = pulp_db.execute(
                    select(UpdateRecord).where(
                        UpdateRecord.content_ptr_id == collection.update_record_id
                    )
                ).scalars().first()

                if perform_updates:
                    new_update_package = UpdatePackage(
                        update_collection_id=collection.pulp_id,
                        name=pulp_pkg["name"],
                        filename=pulp_pkg["location_href"],
                        arch=pulp_pkg["arch"],
                        version=pulp_pkg["version"],
                        release=pulp_pkg["release"],
                        epoch=str(pulp_pkg["epoch"]),
                        reboot_suggested=missing_pkg.errata_package.reboot_suggested,
                        src=pulp_pkg["rpm_sourcerpm"],
                        sum=pulp_pkg["pkgId"] if not pulp_pkg["sha256"] else pulp_pkg["sha256"],
                        sum_type=cr.checksum_type("sha256"),
                    )

                    pulp_db.add(new_update_package)
                    pulp_record.updated_date = datetime.datetime.utcnow().strftime(
                        "%Y-%m-%d %H:%M:%S"
                    )

                repos_for_publication.add((repo_name, repo_href))
    return repos_for_publication


async def main():
    args = parse_args()
    if args.perform_updates:
        logging.warning(
            "The script was called with --perform-updates. " \
            "Changes will be applied in production repositories"
        )
    else:
        logging.warning(
            "The script was called without --perform-updates and the changes " \
            "will not be applied in production repositories. " \
            "This way you can see the changes that will be done in production " \
            "repositories without actually perfoming them." \
        )

    repos_for_publication = set()

    pulp = pulp_client.PulpClient(
        settings.pulp_host, settings.pulp_user, settings.pulp_password
    )

    # Retrieve errata_to_albs_packages whose arch in (x86_64, i686, noarch) and status is 'released'
    released_intel_albs_packages = get_released_intel_errata_to_albs_packages()

    for albs_record, albs_pkgs in released_intel_albs_packages.items():
        pulp_intel_collections = await get_intel_update_collections(albs_record)
        if not pulp_intel_collections:
            # If there are no collections, then I'd say it has not been released
            # and we can keep going
            logging.info(f"{albs_record}: Not released")
            continue

        pulp_intel_collections_pkgs = []
        for collection in pulp_intel_collections:
            if not collection.packages:
                continue
            pulp_intel_collections_pkgs.extend(collection.packages)

        if not pulp_intel_collections_pkgs:
            logging.info(f"{albs_record}: No packages found in Pulp")
            continue

        albs_pkgs_human_readable = set([(pkg.name, pkg.arch) for pkg in albs_pkgs])
        pulp_pkgs_human_readable = set([(pkg.name, pkg.arch) for pkg in pulp_intel_collections_pkgs])
        missing_human_readable = albs_pkgs_human_readable.difference(pulp_pkgs_human_readable)
        if missing_human_readable:
            logging.info(f"{albs_record}: Missing packages: {missing_human_readable}")
            missing = set([
                pkg for pkg in albs_pkgs
                if (pkg.name, pkg.arch) in missing_human_readable
            ])
            repos_to_update = await add_missing_pkgs_to_pulp_update_collections(
                pulp,
                missing,
                pulp_intel_collections,
                args.perform_updates
            )
            repos_for_publication.update(repos_to_update)

    # Make a new publication of every updated repository
    for repo_name, repo_href in repos_for_publication:
        logging.info(f"Re-publicating {repo_name}: {repo_href}")
        if args.perform_updates:
            await pulp.create_rpm_publication(repo_href)


if __name__ == "__main__":
    pulp_client.PULP_SEMAPHORE = asyncio.Semaphore(10)
    asyncio.run(main())

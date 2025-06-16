# BS-490: Add x86_64_v2 errata packages to already released erratas
# Issue: https://github.com/AlmaLinux/build-system/issues/490
# Author: Javi Hernández <javi@almalinux.org>
#
# This script does the following:
#   1. Take the already released erratas - ✔
#   2. For every errata, duplicate x86_64 packages into x86_64_v2 and noarch in database
#   3. Add corresponding errata_to_albs_packages of x86_64_v2 errata packages (and their corresponding noarch)
#   4. Release into pulp - only for x86_64_v2 collections
#   5. Generate new oval data
#   6. Update release log

import argparse
import asyncio
import logging
import os
import re 
import sys

from collections import defaultdict 

from fastapi_sqla import open_async_session
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from alws import models
from alws.config import settings
from alws.crud.errata import (
    get_albs_oval_cache,
    add_oval_data_to_errata_record,
    load_platform_packages,
    get_matching_albs_packages,
    generate_query_for_release,
    get_albs_packages_from_record,
    process_errata_release_for_repos,
    get_release_logs,
)
from alws.dependencies import get_async_db_key
from alws.utils.fastapi_sqla_setup import setup_all
from alws.utils.pulp_client import PulpClient

logging.basicConfig(level=logging.INFO)

# 18 released erratas until 13 Jun 2025
errata_ids = [
    "ALSA-2025:7500", "ALSA-2025:7509", "ALSA-2025:7517", "ALSA-2025:7524",
    "ALSA-2025:7593", "ALSA-2025:7599", "ALSA-2025:7601", "ALSA-2025:8047",
    "ALSA-2025:8125", "ALSA-2025:8128", "ALSA-2025:8131", "ALSA-2025:8184",
    "ALSA-2025:8196", "ALSA-2025:8477", "ALSA-2025:8493", "ALSA-2025:8550",
    "ALSA-2025:8608", "ALSA-2025:8814"
]

albs_oval_cache = defaultdict()

# We need a script that:
async def get_errata_records(db):
    db_errata_records_q = (
        select(models.NewErrataRecord)
        .where(
            models.NewErrataRecord.id.in_(errata_ids)
        )
        .options(
            selectinload(models.NewErrataRecord.references),
            selectinload(models.NewErrataRecord.packages)
            .selectinload(models.NewErrataPackage.albs_packages)
            .selectinload(models.NewErrataToALBSPackage.build_artifact),
            selectinload(models.NewErrataRecord.platform).selectinload(
                models.Platform.repos
            ),
        )
        .with_for_update()
    )
    return (await db.execute(db_errata_records_q)).scalars().all()

async def make_oval_cache(db):
    for platform in ['AlmaLinux-10']:
        logging.info(f"Preparing OVAL cache for {platform}")
        albs_oval_cache[platform] = await get_albs_oval_cache(db, platform)

def generate_v2_package_dicts(packages):
    clean_pkgs = []
    for pkg in packages:
        pkg_dict = dict(pkg.__dict__)
        for k in ("_sa_instance_state", "albs_packages", "id"):
            pkg_dict.pop(k)
        if pkg_dict["arch"] == "x86_64":
            pkg_dict["arch"] = "x86_64_v2"
        clean_pkgs.append(pkg_dict)
    return clean_pkgs

def prepare_search_params(packages):
    search_params = defaultdict(list)
    for package in packages:
        for attr in ("name", "version", "epoch"):
            value = str(getattr(package, attr))
            if value in search_params[attr]:
                continue
            search_params[attr].append(value)
    return search_params

async def add_v2_packages(db, errata):
    # compile both x86_64and noarch to duplicate for x86_64_v2
    x86_64_pkgs = [
        pkg for pkg in errata.packages
        if pkg.arch == "x86_64"
    ]
    noarch_pkgs = {}
    for pkg in errata.packages:
        if pkg.arch != "noarch" or pkg.name in noarch_pkgs.keys():
            continue
        noarch_pkgs[pkg.name] = pkg
    x86_64_pkgs.extend(noarch_pkgs.values())
    # generate errata packages
    new_package_dicts = generate_v2_package_dicts(x86_64_pkgs)
    new_errata_packages = [
        models.NewErrataPackage(**pkg_dict)
        for pkg_dict in new_package_dicts
    ]
    # add errata packages to errata record
    errata.packages.extend(new_errata_packages)
    # generate errata_to_albs_packages
    search_params = prepare_search_params(new_errata_packages)
    prod_repos_cache = await load_platform_packages(
        errata.platform, search_params
    )
    # just in case I need to debug
    #all_matching_packages = []
    for pkg in new_errata_packages:
        matching_packages, _ = await get_matching_albs_packages(
            db, pkg, prod_repos_cache
        )
        #all_matching_packages.extend(matching_packages)
    await db.commit()

async def release_x86_64_v2_errata(
    session, record_id: str, platform_id: int, force: bool
):
    pulp = PulpClient(
        settings.pulp_host,
        settings.pulp_user,
        settings.pulp_password,
    )
    query = generate_query_for_release([record_id])
    query = query.filter(models.NewErrataRecord.platform_id == platform_id)
    db_record = await session.execute(query)
    db_record: Optional[models.NewErrataRecord] = (
        db_record.scalars().first()
    )
    if not db_record:
        logging.info("Record with %s id doesn't exists", record_id)
        return

    logging.info("Record release %s has been started", record_id)
    search_params = prepare_search_params(db_record.packages)
    logging.info("Retrieving platform packages from pulp")
    pulp_packages = await load_platform_packages(
        db_record.platform,
        search_params,
        for_release=True,
    )
    try:
        repo_mapping, missing_pkg_names = get_albs_packages_from_record(
            db_record,
            pulp_packages,
            force,
        )
    except Exception as exc:
        # Don't need to do this
        #db_record.release_status = ErrataReleaseStatus.FAILED
        #db_record.last_release_log = str(exc)
        logging.exception("Cannot release %s record:", record_id)
        await session.flush()
        return

    repos = await pulp.get_rpm_repositories_by_params(
        {
            "pulp_href__in": ",".join(list(repo_mapping.keys())),
            "fields": ["name", "pulp_href"]
        }
    )
    repos_to_skip = [
        repo["pulp_href"]
        for repo in repos
        if "x86_64_v2" not in repo["name"]
    ]
    for repo in repos_to_skip:
        repo_mapping.pop(repo)
    logging.info("Creating update record in pulp")
    await process_errata_release_for_repos(
        db_record,
        repo_mapping,
        session,
        pulp,
    )

    logging.info("Generating OVAL data")
    oval_cache = albs_oval_cache[db_record.platform.name]
    await add_oval_data_to_errata_record(db_record, oval_cache)

    # I don't need to set it as RELEASED
    #db_record.release_status = ErrataReleaseStatus.RELEASED
    # Here, I must update the last_release_log to include the x86_64_v2 addition
    last_release_log = await get_release_logs(
        record_id=record_id,
        pulp_packages=pulp_packages,
        session=session,
        repo_mapping=repo_mapping,
        db_record=db_record,
        force_flag=force,
        missing_pkg_names=missing_pkg_names,
    )
    db_record.last_release_log = (
        str(db_record.last_release_log)
        + "\n\n** Re-released for x86_64_v2 arch addition **\n"
        + last_release_log
    )
    await session.flush()
    logging.info("Record %s successfully released", record_id)

async def process_errata_record(db, errata_record: models.NewErrataRecord):
    logging.info(f"Adding x86_64_v2 errata packages to {errata_record.id}")
    oval_cache = albs_oval_cache[errata_record.platform.name]
    # Duplicate x86_64 (and corresponding noarch) into x86_64_v2
    await add_v2_packages(db, errata_record)
    # Add/release x86_64_v2 errata info - DO NOT TOUCH OTHER REPOS IN PULP!!
    await release_x86_64_v2_errata(
        db, errata_record.id, errata_record.platform_id, True
    )
    logging.info(f"Successfully added x86_64_v2 packages to {errata_record.id}")

async def add_x86_64_v2_errata_pkgs():
    await setup_all()
    async with open_async_session(key=get_async_db_key()) as db:
        await make_oval_cache(db)
        errata_records = await get_errata_records(db)
        for errata_record in errata_records:
            logging.info(f"Processing {errata_record.id}")
            await process_errata_record(db, errata_record)
    logging.info(f"Finished processing affected erratas")



if __name__ == '__main__':
    asyncio.run(add_x86_64_v2_errata_pkgs())

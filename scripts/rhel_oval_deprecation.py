import os
import sys

import argparse
import json
import logging
import re

from collections import defaultdict
from typing import List

from fastapi_sqla import open_async_session
from hawkey import split_nevra
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from syncer import sync

from almalinux.liboval.composer import Composer
from almalinux.liboval.data_generation import (
    Module, OvalDataGenerator, Platform
)

from alws import models
from alws.config import settings
from alws.constants import ErrataReleaseStatus
from alws.crud.errata import get_oval_xml
from alws.dependencies import get_async_db_key
from alws.utils.fastapi_sqla_setup import setup_all

sys.path.append(os.path.dirname(os.path.dirname(__file__)))

ALMALINUX_PLATFORMS = ["AlmaLinux-8", "AlmaLinux-9"]

logging.basicConfig()
logger = logging.getLogger(__name__)
logger.setLevel('DEBUG')

async def get_platform_oval_data(
    session: AsyncSession, platform_name: str
) -> dict:
    xml_string = await get_oval_xml(session, platform_name, True)
    oval = Composer.load_from_string(xml_string)
    oval_dict = oval.as_dict()
    return oval_dict


async def get_platform_erratas(
    session: AsyncSession, platform_name: str
) -> List[models.NewErrataRecord]:
    query = select(models.NewErrataRecord).where(
        models.NewErrataRecord.release_status == ErrataReleaseStatus.RELEASED
    ).options(
        selectinload(models.NewErrataRecord.platform),
        selectinload(models.NewErrataRecord.packages)
        .selectinload(models.NewErrataPackage.albs_packages),
        selectinload(models.NewErrataRecord.references)
        .selectinload(models.NewErrataReference.cve),
    )
    platform = await session.execute(
        select(models.Platform).where(models.Platform.name == platform_name)
    )
    platform = platform.scalars().first()
    query = query.filter(models.NewErrataRecord.platform_id == platform.id)
    erratas = (await session.execute(query)).scalars().all()
    return erratas


async def update_debranded_fields(
    errata: models.NewErrataRecord, oval_definition: dict
):
    errata.definition_id = oval_definition["id"]
    errata.oval_title = oval_definition["metadata"]["title"]
    errata.description = oval_definition["metadata"]["description"]
    errata.affected_cpe = oval_definition["metadata"]["advisory"]["affected_cpe_list"]


def find_pkg_criteria_tests(obj):
    pkg_criteria_tests = []

    if isinstance(obj, dict):
        if 'comment' in obj and "is earlier than" in obj['comment']:
            pkg_criteria_tests.append(obj)
        for value in obj.values():
            pkg_criteria_tests.extend(find_pkg_criteria_tests(value))
    elif isinstance(obj, list):
        for item in obj:
            pkg_criteria_tests.extend(find_pkg_criteria_tests(item))

    return pkg_criteria_tests


def get_pkg_arches(tst_id: str, albs_oval_cache: dict) -> List[str]:
    evr_tst = next(
        (
            tst
            for tst in albs_oval_cache["tests"]
            if tst.get("id") == tst_id
        )
    )
    ste = next(
        (
            ste
            for ste in albs_oval_cache["states"]
            if ste["id"] == evr_tst["state_ref"]

        )
    )
    if ste.get("arch"):
        arches = ste["arch"].split("|")
    else:
        arches = ["noarch"]
    return arches


def prepare_pkgs_for_oval(
    oval_definition: dict, albs_oval_cache: dict
) -> List[dict]:
    oval_pkgs = []
    oval_pkgs_by_name = defaultdict(list)
    pkg_tests = find_pkg_criteria_tests(oval_definition["criteria"])
    for pkg_test in pkg_tests:
        regex = re.compile('^(?P<name>.*) is earlier than (?P<evr>.*)$')
        match = regex.search(pkg_test["comment"])
        pkg_name = match.groupdict()["name"]
        pkg_evr = match.groupdict()["evr"]
        # guess arches for this combination of nevras
        arches = get_pkg_arches(pkg_test["ref"], albs_oval_cache)
        for arch in arches:
            nevra = split_nevra(f"{pkg_name}-{pkg_evr}.{arch}")
            oval_pkgs_by_name[nevra.name].append(
                {
                    "name": nevra.name,
                    "epoch": nevra.epoch,
                    "version": nevra.version,
                    "release": nevra.release,
                    "arch": nevra.arch,
                    "reboot_suggested": False
                }
            )

    # Choose the one with the smallest evr among different versions of the same
    # package but in different arches. This situation happens very often, for
    # example, when not all the architectures of a module have been built
    # in the same build.
    smallest_evrs_by_name = {}
    for name, pkgs in oval_pkgs_by_name.items():
        # yes, this could look a bit wild, but we're comparing similar evrs,
        # yell at me if I'm wrong
        smallest_evrs_by_name[name] = min(
            pkgs,
            key=lambda pkg: f'{pkg["epoch"]}:{pkg["version"]}-{pkg["release"]}'
        )

    noarch_pkgs = [
        pkg for pkg in smallest_evrs_by_name.values()
        if pkg["arch"] == "noarch"
    ]

    for name, pkgs in oval_pkgs_by_name.items():
        for pkg in pkgs:
            if pkg["arch"] == "noarch":
                continue
            pkg["epoch"] = smallest_evrs_by_name[name]["epoch"]
            pkg["version"] = smallest_evrs_by_name[name]["version"]
            pkg["release"] = smallest_evrs_by_name[name]["release"]
            oval_pkgs.append(pkg)

    arches = {pkg["arch"] for pkg in oval_pkgs}
    if not arches:
        # This workaround is to cover erratas that only have noarch pkgs, like
        # ALSA-2021:4198. It has no side effects as the state won't take the
        # arch into consideration and the test will pass in every arch.
        arches = {"noarch"}
    for pkg in noarch_pkgs:
        for _ in arches:
            oval_pkgs.append(pkg)

    return oval_pkgs


async def add_oval_data(
    errata: models.NewErrataRecord, oval_definition: dict, albs_oval_cache: dict
):
    oval_packages = prepare_pkgs_for_oval(oval_definition, albs_oval_cache)

    # check if errata includes a devel module
    module = None
    devel_module = None
    if errata.module:
        module = Module(errata.module)
        dev_module = f"{module.name}-devel:{module.stream}"
        if dev_module in errata.original_title:
            devel_module = Module(dev_module)

    oval_ref_ids = {
        "object": [ref["id"] for ref in albs_oval_cache["objects"]],
        "state": [ref["id"] for ref in albs_oval_cache["states"]],
        "test": [ref["id"] for ref in albs_oval_cache["tests"]],
    }

    data_generator = OvalDataGenerator(
        errata.id,
        Platform(errata.platform.name),
        oval_packages,
        logger,
        settings.beholder_host,
        oval_ref_ids,
        module=module,
        devel_module=devel_module,
    )

    objects = data_generator.generate_objects(
        albs_oval_cache["objects"]
    )
    for obj in objects:
        if obj not in albs_oval_cache["objects"]:
            albs_oval_cache["objects"].append(obj)
    errata.objects = objects

    states = data_generator.generate_states(
        albs_oval_cache["states"]
    )
    for ste in states:
        if ste not in albs_oval_cache["states"]:
            albs_oval_cache["states"].append(ste)
    errata.states = states

    tests = data_generator.generate_tests(
        albs_oval_cache["tests"]
    )
    for tst in tests:
        if tst not in albs_oval_cache["tests"]:
            albs_oval_cache["tests"].append(tst)
    errata.tests = tests

    errata.criteria = data_generator.generate_criteria()


async def main(args):
    await setup_all()
    async with open_async_session(key=get_async_db_key()) as session:
        for platform in ALMALINUX_PLATFORMS:
            logger.info("Processing erratas for '%s'", platform)
            items_to_update = []
            albs_oval_cache = await get_platform_oval_data(session, platform)
            erratas = await get_platform_erratas(session, platform)
            for errata in erratas:
                try:
                    oval_defn = next(
                        (
                            defn
                            for defn in albs_oval_cache["definitions"]
                            if defn["metadata"]["title"].startswith(errata.id)
                        )
                    )
                except StopIteration:
                    logger.info(
                        "Skipping '%s' as couldn't be found in OVAL", errata.id
                    )
                    continue
                await update_debranded_fields(errata, oval_defn)
                await add_oval_data(errata, oval_defn, albs_oval_cache)
                items_to_update.append(errata)

            if args.save:
                session.add_all(items_to_update)
                await session.flush()
        await session.commit()


def parse_args():
    parser = argparse.ArgumentParser(
        "rhel_oval_migration",
        description="Add production errata OVAL data into db"
    )
    parser.add_argument(
        "-s",
        "--save",
        action="store_true",
        default=False,
        required=False,
        help="Perform changes in database",
    )
    return parser.parse_args()

if __name__ == "__main__":
    args = parse_args()
    sync(main(args))

import os
import sys

sys.path.append(os.path.dirname(os.path.dirname(__file__)))

import argparse
import logging

import yaml
from syncer import sync

from alws import database
from alws.crud import (
    platform_flavors as pf_crud,
    repository as repo_crud,
)
from alws.schemas import platform_flavors_schema, repository_schema


def parse_args():
    parser = argparse.ArgumentParser(
        "manage_flavours", description="Flavor manage script. Creates flavors"
    )
    parser.add_argument(
        "-c",
        "--config",
        type=str,
        required=True,
        help="Path to config file with flavors description",
    )
    parser.add_argument(
        "-U",
        "--only_update",
        action="store_true",
        default=False,
        required=False,
        help="Updates flavor data in DB",
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        default=False,
        required=False,
        help="Enable verbose output",
    )
    return parser.parse_args()


async def update_flavour(flavour_data: dict, logger: logging.Logger):
    async with database.Session() as db:
        data = platform_flavors_schema.UpdateFlavour(**flavour_data)
        flavor = await pf_crud.update_flavour(db, data)
        if not flavor:
            logger.error("Flavor %s is does not exist", flavour_data["name"])
        else:
            logger.info("Flavor %s update is completed", flavour_data["name"])


async def add_flavor(flavor_data: dict, logger: logging.Logger):
    async with database.Session() as db:
        flavour = await pf_crud.find_flavour_by_name(db, flavor_data["name"])
        if flavour:
            logger.error("Flavor %s is already added", flavor_data["name"])
            return
        data = platform_flavors_schema.CreateFlavour(**flavor_data)
        await pf_crud.create_flavour(db, data)
        logger.info("Flavor %s is added", flavor_data["name"])


def main():
    args = parse_args()
    logger = logging.getLogger("flavor-manager")
    if args.verbose:
        logging.basicConfig(level=logging.DEBUG)
    else:
        logging.basicConfig(level=logging.INFO)
    config_path = os.path.expanduser(os.path.expandvars(args.config))
    with open(config_path, "rt") as f:
        loader = yaml.Loader(f)
        flavours_data = loader.get_data()
    for flavor_data in flavours_data:
        if args.only_update:
            logger.info("Start updating flavor: %s", flavor_data["name"])
            sync(update_flavour(flavor_data, logger))
            continue
        logger.info("Start add flavor: %s", flavor_data["name"])
        sync(add_flavor(flavor_data, logger))


if __name__ == "__main__":
    main()

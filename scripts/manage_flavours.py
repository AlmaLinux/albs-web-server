import os
import sys

sys.path.append(os.path.dirname(os.path.dirname(__file__)))

import argparse
import logging

import yaml
from syncer import sync

from alws import database
from alws.crud import platform_flavors as pf_crud
from alws.crud import repository as repo_crud
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
        "-p",
        "--prune",
        action="store_true",
        default=False,
        required=False,
        help="Prune flavours on database but not in config",
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        default=False,
        required=False,
        help="Enable verbose output",
    )
    parser.add_argument(
        "-y",
        "--yes",
        action="store_true",
        default=False,
        required=False,
        help="Anser \"yes\" to confirmation",
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


async def prune_flavours(
    flavours_data: [], logger: logging.Logger, confirmation_yes
):
    async with database.Session() as db:
        flavour_names_in_config = [e.get('name') for e in flavours_data]
        flavours_in_db = await pf_crud.list_flavours(db)

        logger.info(
            "Found %d flavours in database, %d flavours in config",
            len(flavours_in_db),
            len(flavours_data),
        )

        orphaned_flavours = []
        for flavour in flavours_in_db:
            if flavour.name not in flavour_names_in_config:
                orphaned_flavours.append(flavour.id)
                logger.info("\t%s (orphaned)", flavour.name)
            else:
                logger.info("\t%s", flavour.name)

        if not orphaned_flavours:
            logger.info("There's no orphaned flavours, exitting.")
            return

        if confirmation_yes:
            confirmation = 'yes'
        else:
            confirmation = (
                input(
                    "Are you sure want to delete orphaned flavours?\n"
                    "This operation cannot be undone!! (yes/no): "
                )
                == 'yes'
            )

        if confirmation:
            for orphaned_flavour in orphaned_flavours:
                await pf_crud.delete_flavour(db, orphaned_flavour)
            logger.info("Deleted orphaned flavours.")
        else:
            logger.info("Aborted deleting orphaned flavours.")


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

    if args.prune:
        logger.info("Start to prune")
        sync(prune_flavours(flavours_data, logger, args.yes))
        sys.exit(0)
    for flavor_data in flavours_data:
        if args.only_update:
            logger.info("Start updating flavor: %s", flavor_data["name"])
            sync(update_flavour(flavor_data, logger))
            continue
        logger.info("Start add flavor: %s", flavor_data["name"])
        sync(add_flavor(flavor_data, logger))


if __name__ == "__main__":
    main()

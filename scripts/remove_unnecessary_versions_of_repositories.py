# Script: remove_unnecessary_versions_of_repositories.py
# Author:
# - Maxim Petukhov <mpetukhov@cloudlinux.com>
#
# Date: 13 Jan 2023
#
# Description: This script remove unnecessary versions of repositories in pulp:
# - Delete no more than 3 versions of repositories
# - Delete old unsigned builds
#
# Usage: This script requires direct access to both Pulp
# and Build System DBs. For configuration issues ask in
# buildsys-internal channel on CloudLinux Slack.
# This script should be placed inside albs-web-server
# scripts folder as it uses modules inside the repo.
# AFTER running the script PLEASE run "orphans/cleanup" in Pulp
# to remove all orphans artifacts.
# REMEMBER: Do Pulp storoge backup before running the script in
# production just in case anything goes wrong.
#
import argparse
import asyncio
import datetime
import logging
import os
import re
import sys
import typing
import urllib.parse

from fastapi_sqla import open_async_session
from sqlalchemy.future import select

sys.path.append(os.path.dirname(os.path.dirname(__file__)))
from alws import models
from alws.crud import build as build_crud
from alws.dependencies import get_async_db_key
from alws.errors import (
    BuildError,
    DataNotFoundError,
)
from alws.utils.fastapi_sqla_setup import setup_all
from alws.utils.pulp_client import PulpClient


def parse_args():
    parser = argparse.ArgumentParser(
        "pulp_artifacts_remover",
        description="Remove unnecessary versions of repositories in Pulp",
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


# Get old unsigned, unreleased and unrelated builds
async def get_old_unsigned_builds(logger: logging.Logger):
    async with open_async_session(key=get_async_db_key()) as db:
        build_dependency = select(
            models.BuildDependency.c.build_dependency
        ).scalar_subquery()
        build_dependent = select(
            models.BuildDependency.c.build_id
        ).scalar_subquery()
        product_packages = select(
            models.ProductBuilds.c.build_id
        ).scalar_subquery()
        query = select(models.Build).where(
            models.Build.id.not_in(build_dependency),
            models.Build.id.not_in(build_dependent),
            models.Build.id.not_in(product_packages),
            models.Build.released.is_(False),
            models.Build.signed.is_(False),
            models.Build.created_at <= datetime.date(2022, 1, 31),
        )
        builds = await db.execute(query)
    result = builds.scalars().all()
    logger.debug("%s old unsigned builds received from DB", len(result))
    return result


async def remove_builds(builds: list, logger: logging.Logger):
    for build in builds:
        async with open_async_session(key=get_async_db_key()) as db:
            try:
                logger.debug("Delete build with id: %s", build.id)
                await build_crud.remove_build_job(db, build.id)
                logger.debug("Build with id %s has been deleted", build.id)
            except DataNotFoundError as err:
                logger.error(err)
            except BuildError as err:
                logger.error(err)


# Change retain_repo_versions to min value and return it back
# After changing the retain_repo_versions Pulp will remove unrelated versions
async def remove_unnecessary_versions(
    pulp_client: PulpClient,
    min_retain_repo_versions: int,
    pulp_repo: dict,
    logger: logging.Logger,
):
    endpoint = pulp_repo["pulp_href"]
    if min_retain_repo_versions > pulp_repo["retain_repo_versions"]:
        return
    params = {"retain_repo_versions": min_retain_repo_versions}
    result = await pulp_client.request("PATCH", endpoint, json=params)
    logger.debug(
        "Create task to change retain repo versions to %s",
        params["retain_repo_versions"],
    )
    logger.debug(result)
    params = {"retain_repo_versions": pulp_repo["retain_repo_versions"]}
    result = await pulp_client.request("PATCH", endpoint, json=params)
    logger.debug(
        "Create task to back retain repo versions to %s",
        params["retain_repo_versions"],
    )
    logger.debug(result)


async def get_all_pulp_repositories(
    pulp_client: PulpClient,
    logger: logging.Logger,
):
    endpoint = "pulp/api/v3/repositories/rpm/rpm/"
    params = {"fields": "id,pulp_href,retain_repo_versions"}
    result = []

    def update_result(response: typing.List[dict]):
        for rec in response:
            result.append(rec)

    response = await pulp_client.request("GET", endpoint, params=params)
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
        response = await pulp_client.get_by_href(path)
        update_result(response.get("results", []))
        next_page = response.get("next")
        if not next_page:
            break
    logger.debug("%s repositories received from Pulp", len(result))
    return result


async def main():
    pulp_host = os.environ["PULP_HOST"]
    pulp_user = os.environ["PULP_USER"]
    pulp_password = os.environ["PULP_PASSWORD"]
    args = parse_args()
    logger = logging.getLogger("pulp_artifacts_remover")
    if args.verbose:
        logging.basicConfig(level=logging.DEBUG)
    else:
        logging.basicConfig(level=logging.INFO)
    await setup_all()
    pulp_client = PulpClient(pulp_host, pulp_user, pulp_password)
    logger.info("Get old unsigned builds")
    builds = await get_old_unsigned_builds(logger)
    logger.info("Remove old unsigned builds...")
    await remove_builds(builds, logger)
    logger.info("All old unsigned builds have been deleted")

    logger.info("Get all pulp repos")
    pulp_repos = await get_all_pulp_repositories(pulp_client, logger)
    logger.info("Removing unnecessary versions of repositories...")
    for pulp_repo in pulp_repos:
        await remove_unnecessary_versions(
            pulp_client=pulp_client,
            min_retain_repo_versions=3,
            pulp_repo=pulp_repo,
            logger=logger,
        )
    logger.info("All unnecessary versions of repositories have been deleted")


if __name__ == "__main__":
    asyncio.run(main())

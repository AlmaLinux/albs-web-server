# Script: remove_unnecessary_versions_of_repositories.py
# Author:
# - Maxim Petukhov <mpetukhov@cloudlinux.com>
#
# Date: 13 Jan 2023
#
# Description: This script remove unnecessery versions of repositories in pulp:
# - Delete no more than 3 versions of production repositories
# - Delete no more than 2 versions of build repositories
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
import asyncio
import os
import sys
import argparse
import typing
import re
import logging
import urllib.parse

sys.path.append(os.path.dirname(os.path.dirname(__file__)))

from alws.utils.pulp_client import PulpClient


def parse_args():
    parser = argparse.ArgumentParser(
        "pulp_artifacts_remover",
        description="Remove unnecessery versions of repositories in Pulp",
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


# Change retain_repo_versions to min value and return it back
# After changing the retain_repo_versions Pulp will remove unrelated versions
async def remove_unnecessery_versions(
    pulp_client: PulpClient,
    min_retain_repo_versions: int,
    pulp_repo: dict,
    logger: logging.Logger,
):
    endpoint = pulp_repo["pulp_href"]
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
        params["retain_repo_versions"]
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
    pulp_client = PulpClient(pulp_host, pulp_user, pulp_password)
    logger.info("Get all pulp repos")
    pulp_repos = await get_all_pulp_repositories(pulp_client, logger)
    logger.info("Removing unnecessery versions of repositories...")
    for pulp_repo in pulp_repos:
        await remove_unnecessery_versions(
            pulp_client=pulp_client,
            min_retain_repo_versions=3,
            pulp_repo=pulp_repo,
            logger=logger,
        )
    logger.info("All unnecessery version of repositories is deleted")


if __name__ == "__main__":
    asyncio.run(main())

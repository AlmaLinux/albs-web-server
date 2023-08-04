import argparse
import asyncio
import itertools
import logging
import pprint
import typing

from alws.utils.pulp_client import PulpClient
from scripts.utils.pulp import get_pulp_params


PROG_NAME = "backup_beta_repositories"
ReposType = typing.List[typing.Dict[str, typing.Any]]


async def find_pulp_repos(
        name_starts: str,
        pulp_client: typing.Optional[PulpClient] = None
) -> ReposType:
    if not pulp_client:
        host, user, password = get_pulp_params()
        pulp_client = PulpClient(host, user, password)
    repositories = await pulp_client.get_rpm_repositories_by_params(
        {"name__startswith": name_starts})
    repositories = [r for r in repositories if "backup" not in r["name"]]

    return repositories


async def create_pulp_backup_repos(
        repos: ReposType,
        dry_run: bool = False,
        pulp_client: typing.Optional[PulpClient] = None
) -> typing.Dict[str, typing.Dict[str, typing.Any]]:
    logger = logging.getLogger(PROG_NAME)
    if not pulp_client:
        host, user, password = get_pulp_params()
        pulp_client = PulpClient(host, user, password)

    result = {}
    for repo in repos:
        backup_repo_name = f"{repo['name']}-backup"
        if dry_run:
            result[repo["name"]] = {"name": backup_repo_name, "pulp_href": ""}
            continue
        backup_repo = await pulp_client.get_rpm_repository(backup_repo_name)
        if not backup_repo:
            url, href = await pulp_client.create_rpm_repository(
                backup_repo_name, create_publication=True,
                base_path_start="backups"
            )
            logger.info("Backup repository URL: %s, href: %s", url, href)
            backup_repo = await pulp_client.get_rpm_repository(backup_repo_name)
        result[repo["name"]] = backup_repo
    return result


async def _main(dry_run: bool = False):
    logger = logging.getLogger(PROG_NAME)
    logger.debug("Acquiring Pulp connection data and creating client")
    host, user, password = get_pulp_params()
    pulp_client = PulpClient(host, user, password)
    logger.info("Searching for all beta repositories")
    repos = await find_pulp_repos("almalinux8-beta", pulp_client=pulp_client)
    repos.extend(await find_pulp_repos(
        "AlmaLinux-9-beta", pulp_client=pulp_client))
    backup_repos = await create_pulp_backup_repos(repos, dry_run=dry_run)
    fields = ["pulp_href", "sha256"]
    add_tasks = []
    remove_tasks = []
    publications_tasks = []
    for repo in repos:
        hrefs = []
        logger.info("Processing repository %s", repo["name"])
        version_href = repo["latest_version_href"]
        logger.debug("Version href: %s", version_href)
        pkgs = await pulp_client.get_rpm_packages(
            include_fields=fields,
            repository_version=version_href,
            limit=1000
        )
        modules = await pulp_client.get_modules(
            repository_version=version_href
        )
        for entity in itertools.chain(pkgs, modules):
            hrefs.append(entity["pulp_href"])
        backup_repo = backup_repos[repo["name"]]
        logger.info("Backup repository: %s", str(backup_repo))
        backup_repo_href = backup_repo["pulp_href"]
        logger.info("Packages and modules for %s are gathered", repo["name"])
        logger.debug("Hrefs to backup: %s", pprint.pformat(hrefs))
        if dry_run:
            continue

        if hrefs:
            add_tasks.append(
                pulp_client.modify_repository(backup_repo_href, add=hrefs)
            )
            if not backup_repo.get("autopublish", False):
                publications_tasks.append(
                    pulp_client.create_rpm_publication(backup_repo_href)
                )
            remove_tasks.append(
                pulp_client.modify_repository(
                    repo["pulp_href"], add=[], remove=hrefs)
            )
            if not repo.get("autopublish", False):
                publications_tasks.append(
                    pulp_client.create_rpm_publication(repo["pulp_href"])
                )

    if add_tasks:
        logger.info("Starting all modifications tasks")
        await asyncio.gather(*add_tasks)
        logger.info("Tasks are finished")
    if remove_tasks:
        logger.info("Processing deletion tasks")
        await asyncio.gather(*remove_tasks)
        logger.info("Tasks are finished")
    if publications_tasks:
        logger.info("Running publications tasks")
        await asyncio.gather(*publications_tasks)
        logger.info("Publications tasks are finished")


def main():
    parser = argparse.ArgumentParser(PROG_NAME)
    parser.add_argument("-v", "--verbose", action="store_true", default=False,
                        help="Enable verbose output")
    parser.add_argument("-d", "--dry-run", action="store_true", default=False,
                        help="Output everything that will happen, "
                             "but do not create/modify anything")
    args = parser.parse_args()
    level = logging.DEBUG if args.verbose else logging.INFO
    logging.basicConfig(level=level)
    asyncio.run(_main(dry_run=args.dry_run))


if __name__ == "__main__":
    main()

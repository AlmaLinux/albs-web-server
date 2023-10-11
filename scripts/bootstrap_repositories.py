import os
import sys
import typing

sys.path.append(os.path.dirname(os.path.dirname(__file__)))

import argparse
import logging

import yaml
from syncer import sync

from alws import database
from alws.crud import platform as pl_crud
from alws.crud import repository as repo_crud
from alws.schemas import platform_schema, remote_schema, repository_schema
from alws.utils.pulp_client import PulpClient


def parse_args():
    parser = argparse.ArgumentParser(
        "bootstrap_repositories",
        description="Repository bootstrap script. Creates repositories "
        "in Pulp for further usage",
    )
    parser.add_argument(
        "-R",
        "--no-remotes",
        action="store_true",
        default=False,
        required=False,
        help="Disable creation of repositories remotes",
    )
    parser.add_argument(
        "-S",
        "--no-sync",
        action="store_true",
        default=False,
        required=False,
        help="Do not sync repositories with " "corresponding remotes",
    )
    parser.add_argument(
        "-c",
        "--config",
        type=str,
        required=True,
        help="Path to config file with repositories description",
    )
    parser.add_argument(
        "-U",
        "--only_update",
        action="store_true",
        default=False,
        required=False,
        help="Updates platform data in DB",
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


async def get_repository(
    pulp_client: PulpClient,
    repo_info: dict,
    repo_name: str,
    production: bool,
    logger: logging.Logger,
):
    async with database.Session() as db:
        if production:
            repo_payload = repo_info.copy()
            repo_payload.pop("remote_url")
            repo = await pulp_client.get_rpm_repository(repo_name)
            if repo:
                distro = await pulp_client.get_rpm_distro(repo_name)
                if not distro:
                    distro = await pulp_client.create_rpm_distro(
                        repo_name, repo["pulp_href"], base_path_start="prod"
                    )
                repo_url = distro["base_url"]
                repo_href = repo["pulp_href"]
            else:
                repo_url, repo_href = await pulp_client.create_rpm_repository(
                    repo_name, create_publication=True, base_path_start="prod"
                )
            logger.debug("Base URL: %s, Pulp href: %s", repo_url, repo_href)
            payload_dict = repo_payload.copy()
            payload_dict["url"] = repo_url
            payload_dict["pulp_href"] = repo_href
            repository = await repo_crud.search_repository(
                db, repository_schema.RepositorySearch(**payload_dict)
            )
            if not repository:
                repository = await repo_crud.create_repository(
                    db, repository_schema.RepositoryCreate(**payload_dict)
                )
            elif repository.pulp_href != repo_href:
                logger.info(
                    'Founded repository by data %s has another pulp_href %s',
                    payload_dict,
                    repository.pulp_href,
                )
                repository = await repo_crud.update_repository(
                    db=db,
                    repository_id=repository.id,
                    payload=repository_schema.RepositoryUpdate(
                        **{
                            'pulp_href': repo_href,
                        }
                    ),
                )

        else:
            payload = repo_info.copy()
            payload["url"] = payload["remote_url"]
            repository = await repo_crud.search_repository(
                db, repository_schema.RepositorySearch(**payload)
            )
            if not repository:
                repository = await repo_crud.create_repository(
                    db, repository_schema.RepositoryCreate(**payload)
                )
    return repository


async def get_remote(repo_info: dict, remote_sync_policy: str):
    async with database.Session() as db:
        remote_payload = repo_info.copy()
        remote_payload["name"] = f'{repo_info["name"]}-{repo_info["arch"]}'
        remote_payload.pop("type", None)
        remote_payload.pop("debug", False)
        remote_payload.pop("production", False)
        remote_payload["url"] = remote_payload["remote_url"]
        remote_payload["policy"] = remote_sync_policy
        remote = await repo_crud.create_repository_remote(
            db, remote_schema.RemoteCreate(**remote_payload)
        )
        return remote


async def update_remote(remote_id, remote_data: dict):
    async with database.Session() as db:
        return await repo_crud.update_repository_remote(
            db=db,
            remote_id=remote_id,
            payload=remote_schema.RemoteUpdate(**remote_data),
        )


async def update_platform(platform_data: dict):
    async with database.Session() as db:
        await pl_crud.modify_platform(
            db, platform_schema.PlatformModify(**platform_data)
        )


async def update_repository(repo_id: int, repo_data: dict):
    async with database.Session() as db:
        await repo_crud.update_repository(
            db, repo_id, repository_schema.RepositoryUpdate(**repo_data)
        )


async def get_repositories_for_update(platform_name: str):
    async with database.Session() as db:
        return await repo_crud.get_repositories_by_platform_name(
            db, platform_name
        )


async def add_repositories_to_platform(
    platform_data: dict, repositories_ids: typing.List[int]
):
    platform_name = platform_data.get("name")
    platform_instance = None
    async with database.Session() as db:
        for platform in await pl_crud.get_platforms(
            db, is_reference=platform_data.get("is_reference", False)
        ):
            if platform.name == platform_name:
                platform_instance = platform
                break
        if not platform_instance:
            platform_instance = await pl_crud.create_platform(
                db, platform_schema.PlatformCreate(**platform_data)
            )
        await repo_crud.add_to_platform(
            db, platform_instance.id, repositories_ids
        )


def main():
    pulp_host = os.environ["PULP_HOST"]
    pulp_user = os.environ["PULP_USER"]
    pulp_password = os.environ["PULP_PASSWORD"]
    args = parse_args()
    logger = logging.getLogger("repo-bootstrapper")
    if args.verbose:
        logging.basicConfig(level=logging.DEBUG)
    else:
        logging.basicConfig(level=logging.INFO)
    config_path = os.path.expanduser(os.path.expandvars(args.config))
    with open(config_path, "rt") as f:
        loader = yaml.Loader(f)
        platforms_data = loader.get_data()

    pulp_client = PulpClient(pulp_host, pulp_user, pulp_password)

    for platform_data in platforms_data:
        if args.only_update:
            sync(update_platform(platform_data))
            platform_name = platform_data.get("name")
            logger.info(
                "Updating %s platform data is completed",
                platform_name,
            )
            db_repos = sync(get_repositories_for_update(platform_name))
            repos_to_update = {}
            for repo in platform_data.get("repositories", []):
                for db_repo in db_repos:
                    conditions = (
                        db_repo.name == repo["name"],
                        db_repo.arch == repo["arch"],
                        db_repo.type == repo["type"],
                        db_repo.debug == repo["debug"],
                    )
                    if all(conditions):
                        repos_to_update[db_repo.id] = repo
                        break
            logger.info(
                "Start updating repository data for platform: %s",
                platform_name,
            )
            for repo_id, repo_data in repos_to_update.items():
                sync(update_repository(repo_id, repo_data))
            logger.info(
                "Updating repository data for platform %s is completed",
                platform_name,
            )
            continue
        if not platform_data.get("repositories"):
            logger.info("Config does not contain a list of repositories")

        repository_ids = []
        repositories_data = platform_data.pop("repositories", [])

        for repo_info in repositories_data:
            logger.info(
                "Creating repository from the following data: %s",
                str(repo_info),
            )
            # If repository is not marked as production, do not remove `url` field
            repo_name = f'{repo_info["name"]}-{repo_info["arch"]}'
            is_production = repo_info.get("production", False)
            repo_sync_policy = repo_info.pop("repository_sync_policy", None)
            remote_sync_policy = repo_info.pop("remote_sync_policy", None)
            repository = sync(
                get_repository(
                    pulp_client, repo_info, repo_name, is_production, logger
                )
            )
            repository_ids.append(repository.id)

            logger.debug("Repository instance: %s", repository)
            if args.no_remotes:
                logger.warning(
                    "Not creating a remote for repository %s", repository
                )
                continue
            if not is_production:
                logger.info(
                    "Repository %s is not marked as production and "
                    "does not need remote setup",
                    repository,
                )
                continue

            remote = sync(get_remote(repo_info, remote_sync_policy))
            pulp_remote = sync(
                pulp_client.get_rpm_remote(
                    f'{repo_info["name"]}-{repo_info["arch"]}',
                )
            )
            if pulp_remote['pulp_href'] != remote.pulp_href:
                remote = sync(
                    update_remote(
                        remote_id=remote.id,
                        remote_data={
                            'name': remote.name,
                            'pulp_href': pulp_remote['pulp_href'],
                            'arch': remote.arch,
                            'url': remote.url,
                        },
                    )
                )
            if args.no_sync:
                logger.info(
                    "Synchronization from remote is disabled, skipping"
                )
                continue
            try:
                logger.info("Syncing %s from %s...", repository, remote)
                sync(
                    pulp_client.sync_rpm_repo_from_remote(
                        repository.pulp_href,
                        remote.pulp_href,
                        sync_policy=repo_sync_policy,
                        wait_for_result=True,
                    )
                )
                sync(pulp_client.create_rpm_publication(repository.pulp_href))
                logger.info("Repository %s sync is completed", repository)
            except Exception as e:
                logger.info(
                    "Repository %s sync is failed: \n%s", repository, str(e)
                )
        sync(add_repositories_to_platform(platform_data, repository_ids))


if __name__ == "__main__":
    main()

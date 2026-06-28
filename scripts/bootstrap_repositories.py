import asyncio
import os
import sys
import typing

sys.path.append(os.path.dirname(os.path.dirname(__file__)))

import argparse
import logging

import yaml
from fastapi_sqla import open_async_session
from sqlalchemy import update

from alws import models
from alws.crud import platform as pl_crud
from alws.crud import repository as repo_crud
from alws.dependencies import get_async_db_key
from alws.schemas import platform_schema, remote_schema, repository_schema
from alws.utils import pulp_client as pulp_client_module
from alws.utils.fastapi_sqla_setup import setup_all
from alws.utils.pulp_client import PulpClient
from scripts.bootstrap_permissions import ensure_system_user_exists

REPO_CACHE = {}
BOOTSTRAP_CONCURRENCY = int(os.environ.get("BOOTSTRAP_CONCURRENCY", "10"))


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
        "--use-remote-url",
        action="store_true",
        default=False,
        required=False,
        help="Use remote_url directly as the repository URL even for "
        "production repos, skipping Pulp repo/remote creation and sync. "
        "Intended for dev instances that should not sync from remotes.",
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
    async with open_async_session(key=get_async_db_key()) as db:
        if production:
            repo_payload = repo_info.copy()
            repo_payload.pop("remote_url")
            if repo_name in REPO_CACHE:
                repo_url, repo_href = REPO_CACHE[repo_name]
            else:
                repo = await pulp_client.get_rpm_repository(repo_name)
                if repo:
                    distro = await pulp_client.get_rpm_distro(repo_name)
                    if not distro:
                        distro = await pulp_client.create_rpm_distro(
                            repo_name,
                            repo["pulp_href"],
                            base_path_start="prod",
                        )
                    repo_url = distro["base_url"]
                    repo_href = repo["pulp_href"]
                else:
                    repo_url, repo_href = (
                        await pulp_client.create_rpm_repository(
                            repo_name,
                            create_publication=True,
                            base_path_start="prod",
                        )
                    )
                REPO_CACHE[repo_name] = (repo_url, repo_href)
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
                    payload=repository_schema.RepositoryUpdate(**{
                        'pulp_href': repo_href,
                    }),
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
    async with open_async_session(key=get_async_db_key()) as db:
        remote_payload = repo_info.copy()
        remote_payload["name"] = (
            f'{repo_info["name"]}-{repo_info["arch"]}-{remote_sync_policy}'
        )
        remote_payload.pop("type", None)
        remote_payload.pop("debug", False)
        remote_payload.pop("production", False)
        remote_payload["url"] = remote_payload["remote_url"]
        remote_payload["policy"] = remote_sync_policy
        if os.getenv("PULP_PROXY_URL"):
            remote_payload["proxy_url"] = os.getenv("PULP_PROXY_URL")
        if os.getenv("PULP_PROXY_USERNAME"):
            remote_payload["proxy_username"] = os.getenv("PULP_PROXY_USERNAME")
        if os.getenv("PULP_PROXY_PASSWORD"):
            remote_payload["proxy_password"] = os.getenv("PULP_PROXY_PASSWORD")
        remote = await repo_crud.create_repository_remote(
            db, remote_schema.RemoteCreate(**remote_payload)
        )
        return remote


async def update_remote(remote_id, remote_data: dict):
    async with open_async_session(key=get_async_db_key()) as db:
        return await repo_crud.update_repository_remote(
            db=db,
            remote_id=remote_id,
            payload=remote_schema.RemoteUpdate(**remote_data),
        )


async def update_platform(platform_data: dict):
    async with open_async_session(key=get_async_db_key()) as db:
        await pl_crud.modify_platform(
            db, platform_schema.PlatformModify(**platform_data)
        )


async def update_repository(repo_id: int, repo_data: dict):
    async with open_async_session(key=get_async_db_key()) as db:
        await repo_crud.update_repository(
            db, repo_id, repository_schema.RepositoryUpdate(**repo_data)
        )


async def get_repositories_for_update(platform_name: str):
    async with open_async_session(key=get_async_db_key()) as db:
        return await repo_crud.get_repositories_by_platform_name(
            db, platform_name
        )


async def add_owner_id():
    async with open_async_session(key=get_async_db_key()) as db:
        system_user = await ensure_system_user_exists(db)
        await db.execute(
            update(models.Platform)
            .where(models.Platform.owner_id.is_(None))
            .values(owner_id=system_user.id)
        )
        await db.execute(
            update(models.Repository)
            .where(models.Repository.owner_id.is_(None))
            .values(owner_id=system_user.id)
        )


async def add_repositories_to_platform(
    platform_data: dict, repositories_ids: typing.List[int]
):
    platform_name = platform_data.get("name")
    platform_instance = None
    async with open_async_session(key=get_async_db_key()) as db:
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


async def populate_repo_cache(
    pulp_client: PulpClient, repositories_data: list
):
    async def fetch(repo_info):
        repo_name = f'{repo_info["name"]}-{repo_info["arch"]}'
        repo = await pulp_client.get_rpm_repository(repo_name)
        if not repo:
            return
        distro = await pulp_client.get_rpm_distro(repo_name)
        if distro:
            REPO_CACHE[repo_name] = (distro["base_url"], repo["pulp_href"])

    sem = asyncio.Semaphore(BOOTSTRAP_CONCURRENCY)

    async def bounded(repo_info):
        async with sem:
            await fetch(repo_info)

    await asyncio.gather(*(bounded(r) for r in repositories_data))


async def process_repository(
    pulp_client: PulpClient,
    repo_info: dict,
    no_remotes: bool,
    no_sync: bool,
    use_remote_url: bool,
    logger: logging.Logger,
):
    """Process a single repo: create repo + remote, return (id, sync_info)."""
    logger.info("Creating repository from the following data: %s", str(repo_info))
    repo_name = f'{repo_info["name"]}-{repo_info["arch"]}'
    is_production = repo_info.get("production", False)
    repo_sync_policy = repo_info.pop("repository_sync_policy", None)
    remote_sync_policy = repo_info.pop("remote_sync_policy", None)

    if use_remote_url and is_production:
        logger.info(
            "use_remote_url is enabled; treating production repo %s as "
            "non-production (remote_url used directly, no Pulp sync)",
            repo_name,
        )
        is_production = False

    repository = await get_repository(
        pulp_client, repo_info, repo_name, is_production, logger
    )
    logger.debug("Repository instance: %s", repository)

    if no_remotes:
        logger.warning("Not creating a remote for repository %s", repository)
        return repository.id, None
    if not is_production:
        logger.info(
            "Repository %s is not marked as production and "
            "does not need remote setup",
            repository,
        )
        return repository.id, None

    remote = await get_remote(repo_info, remote_sync_policy)
    pulp_remote = await pulp_client.get_rpm_remote(
        f'{repo_info["name"]}-{repo_info["arch"]}-{remote_sync_policy}',
    )
    if pulp_remote['pulp_href'] != remote.pulp_href:
        remote = await update_remote(
            remote_id=remote.id,
            remote_data={
                'name': remote.name,
                'pulp_href': pulp_remote['pulp_href'],
                'arch': remote.arch,
                'url': remote.url,
            },
        )
    if no_sync:
        logger.info("Synchronization from remote is disabled, skipping")
        return repository.id, None

    logger.info("Appending %s to sync from %s...", repository, remote)
    return repository.id, {
        'repo_href': repository.pulp_href,
        'remote_href': remote.pulp_href,
        'sync_policy': repo_sync_policy,
    }


async def process_repositories(
    pulp_client: PulpClient,
    repositories_data: list,
    no_remotes: bool,
    no_sync: bool,
    use_remote_url: bool,
    logger: logging.Logger,
):
    sem = asyncio.Semaphore(BOOTSTRAP_CONCURRENCY)

    async def bounded(repo_info):
        async with sem:
            return await process_repository(
                pulp_client,
                repo_info,
                no_remotes,
                no_sync,
                use_remote_url,
                logger,
            )

    return await asyncio.gather(*(bounded(r) for r in repositories_data))


async def sync_repositories(repo_sync_list: list, pulp_client: PulpClient):
    sync_tasks = []
    publish_tasks = []

    async def sync_repo(repo_, remote_, policy):
        logging.info('Syncing repository %s from %s', repo_, remote_)
        try:
            await pulp_client.sync_rpm_repo_from_remote(
                repo_,
                remote_,
                policy,
                wait_for_result=True,
            )
        except Exception:
            logging.exception('Cannot sync repository %s', repo_)

    async def publish_repo(repo_):
        logging.info('Publishing repo %s', repo_)
        try:
            await pulp_client.create_rpm_publication(repo['repo_href'])
        except Exception:
            logging.exception('Cannot publish repository %s', repo_)

    for repo in repo_sync_list:
        sync_tasks.append(
            sync_repo(
                repo['repo_href'],
                repo['remote_href'],
                repo['sync_policy'],
            )
        )
        publish_tasks.append(publish_repo(repo['repo_href']))
    async with asyncio.Semaphore(5):
        await asyncio.gather(*sync_tasks)
        await asyncio.gather(*publish_tasks)


async def main_async():
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

    # Rebind PULP_SEMAPHORE to the current event loop.
    pulp_client_module.PULP_SEMAPHORE = asyncio.Semaphore(BOOTSTRAP_CONCURRENCY)

    pulp_client = PulpClient(pulp_host, pulp_user, pulp_password)

    await setup_all()

    for platform_data in platforms_data:
        if args.only_update:
            await update_platform(platform_data)
            platform_name = platform_data.get("name")
            logger.info(
                "Updating %s platform data is completed",
                platform_name,
            )
            db_repos = await get_repositories_for_update(platform_name)
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
                if args.use_remote_url and repo_data.get("remote_url"):
                    repo_data = {**repo_data, "url": repo_data["remote_url"]}
                await update_repository(repo_id, repo_data)
            logger.info(
                "Updating repository data for platform %s is completed",
                platform_name,
            )
            continue
        if not platform_data.get("repositories"):
            logger.info("Config does not contain a list of repositories")

        repository_ids = []
        repositories_data = platform_data.pop("repositories", [])

        # populate repos cache (parallel, bounded by BOOTSTRAP_CONCURRENCY)
        logger.info('Making repository data cache')
        await populate_repo_cache(pulp_client, repositories_data)

        # process repos in parallel (bounded by BOOTSTRAP_CONCURRENCY)
        results = await process_repositories(
            pulp_client,
            repositories_data,
            args.no_remotes,
            args.no_sync,
            args.use_remote_url,
            logger,
        )
        repos_to_sync = []
        for repo_id, sync_info in results:
            repository_ids.append(repo_id)
            if sync_info is not None:
                repos_to_sync.append(sync_info)
        if repos_to_sync and not args.no_sync:
            await sync_repositories(repos_to_sync, pulp_client)
        await add_repositories_to_platform(platform_data, repository_ids)
        await add_owner_id()


def main():
    asyncio.run(main_async())


if __name__ == "__main__":
    main()

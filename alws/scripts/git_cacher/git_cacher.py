import asyncio
import json
import logging
import typing

import sentry_sdk
from pydantic_settings import BaseSettings
from redis import asyncio as aioredis

from alws.utils.gitea import GiteaClient

__all__ = ['Config', 'load_redis_cache', 'save_redis_cache']


class Config(BaseSettings):
    redis_url: str = 'redis://redis:6379'
    gitea_host: str = 'https://git.almalinux.org/api/v1/'
    git_cache_keys: typing.Dict[str, str] = {
        'rpms': 'rpms_gitea_cache',
        'modules': 'modules_gitea_cache',
        'autopatch': 'autopatch_gitea_cache',
    }
    cacher_sentry_environment: str = "dev"
    cacher_sentry_dsn: str = ""
    cacher_sentry_traces_sample_rate: float = 0.2


async def load_redis_cache(redis: aioredis.Redis, cache_key: str) -> dict:
    value = await redis.get(cache_key)
    if not value:
        return {}
    return json.loads(value)


async def save_redis_cache(redis: aioredis.Redis, cache_key: str, cache: dict):
    await redis.set(cache_key, json.dumps(cache))


def setup_logger():
    logger = logging.getLogger('gitea-cacher')
    logger.setLevel(logging.DEBUG)
    handler = logging.StreamHandler()
    handler.setLevel(logging.DEBUG)
    formatter = logging.Formatter(
        '%(asctime)s [%(name)s:%(levelname)s] - %(message)s'
    )
    handler.setFormatter(formatter)
    logger.addHandler(handler)
    return logger


async def run(
    config: Config,
    logger: logging.Logger,
    redis_client: aioredis.Redis,
    gitea_client: GiteaClient,
    organization: str,
):
    cache = await load_redis_cache(
        redis_client, config.git_cache_keys[organization]
    )
    cache_names = set(repo['full_name'] for repo in cache.values())
    to_index = []
    git_names = set()
    for repo in await gitea_client.list_repos(organization):
        if repo['empty']:
            logger.warning(f"Skipping empty repo {repo['html_url']}")
            continue
        if organization == 'autopatch' and repo['archived']:
            logger.warning(f"Skipping archived repo {repo['html_url']}")
            continue
        repo_name = repo['full_name']
        git_names.add(repo_name)
        repo_meta = {
            'name': repo['name'],
            'full_name': repo_name,
            'updated_at': repo['updated_at'],
            'clone_url': repo['clone_url'],
        }
        if repo_name not in cache:
            cache[repo_name] = repo_meta
            to_index.append(repo_name)
        elif cache[repo_name]['updated_at'] != repo['updated_at']:
            cache[repo_name] = repo_meta
            to_index.append(repo_name)
    results = await asyncio.gather(
        *list(gitea_client.index_repo(repo_name) for repo_name in to_index)
    )
    for result in results:
        cache_record = cache[result['repo_name']]
        cache_record['tags'] = [tag['name'] for tag in result['tags']]
        if organization == 'autopatch':
            cache_record['branches'] = [
                branch
                for branch in result['branches']
                if not branch['name'].endswith('-deprecated')
            ]

        cache_record['branches'] = [
            branch['name'] for branch in result['branches']
        ]
    for outdated_repo in cache_names - git_names:
        cache.pop(outdated_repo)
    await save_redis_cache(
        redis_client, config.git_cache_keys[organization], cache
    )


async def main():
    config = Config()
    if config.cacher_sentry_dsn:
        sentry_sdk.init(
            dsn=config.cacher_sentry_dsn,
            traces_sample_rate=config.cacher_sentry_traces_sample_rate,
            environment=config.cacher_sentry_environment,
        )
    logger = setup_logger()
    redis_client = aioredis.from_url(config.redis_url)
    gitea_client = GiteaClient(config.gitea_host, logger)
    wait = 600
    while True:
        logger.info('Checking cache for updates')
        await asyncio.gather(*(
            run(config, logger, redis_client, gitea_client, organization)
            for organization in (
                # projects git data live in these gitea orgs
                'rpms',
                'modules',
                # almalinux modified packages live in autopatch gitea org
                'autopatch',
            )
        ))
        logger.info(
            'Cache has been updated, waiting for %d secs for next update',
            wait,
        )
        await asyncio.sleep(wait)


if __name__ == '__main__':
    asyncio.run(main())

import asyncio
import json
import logging
import typing

import aioredis
import pydantic

from alws.utils.gitea import GiteaClient


__all__ = ['Config', 'load_redis_cache', 'save_redis_cache']


class Config(pydantic.BaseSettings):

    redis_url: str = 'redis://redis:6379'
    gitea_host: str = 'https://git.almalinux.org/api/v1/'
    git_cache_keys: typing.Dict[str, str] = {
        'rpms': 'rpms_gitea_cache',
        'modules': 'modules_gitea_cache'
    }


async def load_redis_cache(redis, cache_key):
    value = await redis.get(cache_key)
    if not value:
        return {}
    return json.loads(value)


async def save_redis_cache(redis, cache_key, cache):
    await redis.set(cache_key, json.dumps(cache))


def setup_logger():
    logger = logging.getLogger('gitea-cacher')
    logger.setLevel(logging.DEBUG)
    handler = logging.StreamHandler()
    handler.setLevel(logging.DEBUG)
    formatter = logging.Formatter(
        '%(asctime)s [%(name)s:%(levelname)s] - %(message)s')
    handler.setFormatter(formatter)
    logger.addHandler(handler)
    return logger


async def run(config, redis_client, gitea_client, organization):
    cache = await load_redis_cache(
        redis_client, config.git_cache_keys[organization]
    )
    cache_names = set(repo['full_name'] for repo in cache.values())
    to_index = []
    git_names = set()
    for repo in await gitea_client.list_repos(organization):
        repo_name = repo['full_name']
        git_names.add(repo_name)
        repo_meta = {
            'name': repo['name'],
            'full_name': repo_name,
            'updated_at': repo['updated_at'],
            'clone_url': repo['clone_url']
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
        cache_record['branches'] = [
            branch['name'] for branch in result['branches']
        ]
    for outdated_repo in (cache_names - git_names):
        cache.pop(outdated_repo)
    await save_redis_cache(
        redis_client,
        config.git_cache_keys[organization],
        cache
    )


async def main():
    config = Config()
    logger = setup_logger()
    redis_client = aioredis.from_url(config.redis_url)
    gitea_client = GiteaClient(config.gitea_host, logger)
    while True:
        logger.info('Checking cache for updates')
        await asyncio.gather(
            run(config, redis_client, gitea_client, 'rpms'),
            run(config, redis_client, gitea_client, 'modules')
        )
        await asyncio.sleep(600)


if __name__ == '__main__':
    asyncio.run(main())

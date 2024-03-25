from redis import asyncio as aioredis

from alws.config import settings

__all__ = ['get_redis', 'get_async_db_key']


async def get_redis() -> aioredis.Redis:
    client = aioredis.from_url(settings.redis_url)
    try:
        yield client
    finally:
        await client.close()


def get_async_db_key() -> str:
    return "async"

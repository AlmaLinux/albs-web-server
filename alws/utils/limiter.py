from fastapi_limiter import FastAPILimiter
from redis import asyncio as aioredis

from alws.config import settings


async def limiter_startup():
    redis_connection = aioredis.from_url(settings.redis_url)
    await FastAPILimiter.init(redis_connection)


async def limiter_shutdown():
    await FastAPILimiter.close()

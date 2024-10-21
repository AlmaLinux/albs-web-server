from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi_sqla import open_async_session
from redis import asyncio as aioredis
from sqlalchemy.ext.asyncio import AsyncSession

from alws.config import settings

__all__ = ['get_redis', 'get_async_db_key']


async def get_redis() -> AsyncGenerator[aioredis.Redis, None]:
    client = aioredis.from_url(settings.redis_url)
    try:
        yield client
    finally:
        await client.close()


def get_async_db_key() -> str:
    return "async"


@asynccontextmanager
async def get_async_db_session() -> AsyncGenerator[AsyncSession, None]:
    async with open_async_session(key=get_async_db_key()) as session:
        yield session

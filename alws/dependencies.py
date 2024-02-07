import asyncio
from contextlib import contextmanager

from redis import asyncio as aioredis
from sqlalchemy.orm import Session

from alws import database
from alws.config import settings


__all__ = [
    'get_async_session',
    'get_db',
    'get_pulp_db',
    'get_redis',
]


# Usually PostgreSQL supports up to 100 concurrent connections,
# so making semaphore a bit less to not hit that limit
DB_SEMAPHORE = asyncio.Semaphore(90)


# FIXME: `get_current_user` dependency causes a transaction
#  to exist on a connection so we need a separate dependency for it for now.
#  Remove this later when better approach is found.
async def get_async_session() -> database.Session:
    async with DB_SEMAPHORE:
        async with database.Session() as session:
            try:
                yield session
            finally:
                await session.close()


async def get_db() -> database.Session:
    async with DB_SEMAPHORE:
        async with database.Session() as session:
            try:
                yield session
            finally:
                await session.close()


@contextmanager
def get_pulp_db() -> Session:
    with database.PulpSession() as session:
        try:
            yield session
        finally:
            session.close()


async def get_redis() -> aioredis.Redis:
    client = aioredis.from_url(settings.redis_url)
    try:
        yield client
    finally:
        await client.close()

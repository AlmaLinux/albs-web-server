import asyncio
from contextlib import contextmanager

import aioredis

from alws import database
from alws.config import settings


__all__ = [
    'get_pulp_db',
    'get_redis',
]


# Usually PostgreSQL supports up to 100 concurrent connections,
# so making semaphore a bit less to not hit that limit
DB_SEMAPHORE = asyncio.Semaphore(90)


@contextmanager
def get_pulp_db() -> database.PulpSession:
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

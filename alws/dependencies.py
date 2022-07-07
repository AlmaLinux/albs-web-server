import asyncio

import aioredis
from fastapi import Request, HTTPException, status
from fastapi.security import HTTPBearer

from alws import database
from alws.config import settings
from alws.utils.jwt_utils import decode_JWT_token


__all__ = [
    'JWTBearer',
    'get_db',
    'get_pulp_db',
    'get_redis',
]


# Usually PostgreSQL supports up to 100 concurrent connections,
# so making semaphore a bit less to not hit that limit
DB_SEMAPHORE = asyncio.Semaphore(90)


async def get_db() -> database.Session:
    async with DB_SEMAPHORE:
        async with database.Session() as session:
            try:
                yield session
            finally:
                await session.close()


def get_pulp_db() -> database.Session:
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


class JWTBearer(HTTPBearer):

    async def __call__(self, request: Request):
        credentials = await super().__call__(request)
        if not credentials:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail='Invalid authorization code.'
            )
        if credentials.scheme != 'Bearer':
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail='Invalid authentication scheme.'
            )
        identity = self.verify_jwt(credentials.credentials)
        if not identity:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail='Invalid or expired token.'
            )
        return identity

    def verify_jwt(self, token: str) -> dict:
        payload = None
        try:
            payload = decode_JWT_token(
                token,
                settings.jwt_secret,
                settings.jwt_algorithm
            )
        except Exception:
            pass
        return payload

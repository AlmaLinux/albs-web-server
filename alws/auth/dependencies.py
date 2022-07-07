from typing import AsyncGenerator

from fastapi import Depends
from fastapi_users.authentication.strategy import (
    AccessTokenDatabase,
    DatabaseStrategy,
    JWTStrategy,
)
from fastapi_users_db_sqlalchemy import SQLAlchemyUserDatabase
from fastapi_users_db_sqlalchemy.access_token import SQLAlchemyAccessTokenDatabase
from sqlalchemy.ext.asyncio import AsyncSession

from alws.config import settings
from alws.database import Session
from alws.models import User, UserAccessToken, UserOauthAccount

__all__ = [
    'get_access_token_db',
    'get_async_session',
    'get_database_strategy',
    'get_jwt_strategy',
    'get_user_db',
]


async def get_async_session() -> AsyncGenerator[AsyncSession, None]:
    async with Session() as session:
        yield session


async def get_user_db(session: AsyncSession = Depends(get_async_session)):
    yield SQLAlchemyUserDatabase(
        session, User, oauth_account_table=UserOauthAccount)


async def get_access_token_db(
    session: AsyncSession = Depends(get_async_session),
):
    yield SQLAlchemyAccessTokenDatabase(session, UserAccessToken)


def get_database_strategy(
        access_token_db: AccessTokenDatabase = Depends(get_access_token_db)
) -> DatabaseStrategy:
    return DatabaseStrategy(access_token_db, lifetime_seconds=3600)


def get_jwt_strategy() -> JWTStrategy:
    return JWTStrategy(settings.jwt_secret, lifetime_seconds=86400)

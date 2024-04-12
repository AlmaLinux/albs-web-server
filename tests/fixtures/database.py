import os
import typing
from contextlib import asynccontextmanager

import pytest
from sqlalchemy import insert, select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.pool import NullPool

from alws import models
from alws.config import settings
from alws.database import Base
from tests.constants import ADMIN_USER_ID, CUSTOM_USER_ID

engine = create_async_engine(
    os.getenv('DATABASE_URL', settings.test_database_url),
    poolclass=NullPool,
    echo_pool=True,
)


async def get_session():
    async with AsyncSession(
        engine,
        expire_on_commit=False,
    ) as sess:
        try:
            yield sess
        finally:
            await sess.close()


@pytest.mark.anyio
@pytest.fixture
async def session() -> typing.AsyncIterator[AsyncSession]:
    async with asynccontextmanager(get_session)() as db_session:
        yield db_session


def get_user_data():
    return [
        {
            "id": ADMIN_USER_ID,
            "username": "admin",
            "email": "admin@almalinux.com",
            "is_superuser": True,
            "is_verified": True,
        },
        {
            "id": CUSTOM_USER_ID,
            "username": "user1",
            "email": "user1@almalinux.com",
            "is_superuser": False,
            "is_verified": True,
        },
    ]


async def create_user(data: dict):
    data = {
        "id": data["id"],
        "username": data["username"],
        "email": data["email"],
        "is_superuser": data["is_superuser"],
        "is_verified": data["is_verified"],
    }
    async with asynccontextmanager(get_session)() as db_session:
        user = await db_session.execute(
            select(models.User).where(models.User.id == data["id"]),
        )
        if user.scalars().first():
            return
        await db_session.execute(insert(models.User).values(**data))
        await db_session.commit()


@pytest.mark.anyio
@pytest.fixture(scope="module", autouse=True)
async def create_tables():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    for user_data in get_user_data():
        await create_user(user_data)
    yield
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)

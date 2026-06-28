import os

import pytest
from fastapi_sqla import open_async_session
from sqlalchemy import insert, select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm.session import sessionmaker
from sqlalchemy.pool import NullPool

from fastapi_sqla.async_sqla import _async_session_factories
from fastapi_sqla.sqla import _session_factories

from alws import models
from alws.config import settings
from alws.database import Base
from alws.dependencies import get_async_db_key
from alws.utils.fastapi_sqla_setup import setup_all
from tests.constants import ADMIN_USER_ID, CUSTOM_USER_ID


async def reset_session_factories():
    """Dispose and drop cached fastapi-sqla session factories.

    ``setup_all()`` is idempotent: it reuses any session factory that is
    already registered. That is correct in production, where every service
    runs on a single, long-lived event loop. The test suite, however, runs
    each module on its own event loop, so a factory (and its asyncpg pool)
    cached on a previous module's loop would raise "got Future attached to a
    different loop" when reused here. Clearing the caches per module forces
    ``setup_all()`` to rebuild the engines on the current loop.
    """
    for factory in _async_session_factories.values():
        engine = factory.kw.get('bind')
        if engine is not None:
            await engine.dispose()
    _async_session_factories.clear()

    for factory in _session_factories.values():
        engine = factory.kw.get('bind')
        if engine is not None:
            engine.dispose()
    _session_factories.clear()


@pytest.fixture
def async_session_factory():
    """Fastapi-sqla async_session_factory() fixture overload, disabling expire_on_commit."""
    return sessionmaker(class_=AsyncSession, expire_on_commit=False)


@pytest.fixture
async def async_session(
    async_sqla_connection,
    async_session_factory,
    async_sqla_reflection,
    # patch_new_engine
):
    """Fastapi-sqla async_session() fixture overload."""
    session = async_session_factory(bind=async_sqla_connection)
    yield session
    await session.close()


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


async def create_user(async_session: AsyncSession, data: dict):
    data = {
        "id": data["id"],
        "username": data["username"],
        "email": data["email"],
        "is_superuser": data["is_superuser"],
        "is_verified": data["is_verified"],
    }
    user = await async_session.execute(
        select(models.User).where(models.User.id == data["id"]),
    )
    if user.scalars().first():
        return
    await async_session.execute(insert(models.User).values(**data))
    await async_session.commit()


@pytest.fixture(scope="module", autouse=True)
async def create_tables():
    engine = create_async_engine(
        os.getenv('DATABASE_URL', settings.fastapi_sqla__async__sqlalchemy_url),
        poolclass=NullPool,
        echo_pool=True,
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    await reset_session_factories()
    await setup_all()
    async with open_async_session(get_async_db_key()) as async_session:
        for user_data in get_user_data():
            await create_user(async_session, user_data)
    yield

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


@pytest.fixture
def sqla_modules():
    from alws.models import (  # noqa
        Build,
        BuildTask,
        ErrataRecord,
        NewErrataRecord,
        Platform,
        SignKey,
        SignTask,
        Team,
        TestRepository,
        User,
        UserAccessToken,
        UserAction,
        UserOauthAccount,
        UserRole,
    )


@pytest.fixture(scope="session")
def db_url():
    """Fastapi-sqla fixture. Sync database url."""
    return settings.sqlalchemy_url


@pytest.fixture(scope="session")
def async_sqlalchemy_url():
    """Fastapi-sqla fixture. Async database url."""
    return settings.fastapi_sqla__async__sqlalchemy_url


@pytest.fixture(scope="session")
def alembic_ini_path():
    """Fastapi-sqla fixture. Path for alembic.ini file."""
    return "./alws/alembic.ini"

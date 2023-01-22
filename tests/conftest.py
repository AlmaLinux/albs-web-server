from contextlib import asynccontextmanager

import pytest
from sqlalchemy import insert, select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.pool import NullPool
import yaml

from alws import models
from alws.config import settings
from alws.database import Base
from alws.schemas import (
    repository_schema,
    platform_schema,
)
from alws.utils.pulp_client import PulpClient
from tests.constants import ADMIN_USER_ID


engine = create_async_engine(
    settings.test_database_url,
    poolclass=NullPool,
    echo_pool=True,
)


async def get_session():
    async with AsyncSession(engine) as sess:
        try:
            yield sess
        finally:
            await sess.close()


@pytest.fixture(scope="session")
def anyio_backend():
    return "asyncio"


@pytest.fixture(scope="module", autouse=True)
@pytest.mark.anyio
async def create_tables():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


@pytest.fixture
@pytest.mark.anyio
async def session():
    async with asynccontextmanager(get_session)() as session:
        yield session


@pytest.fixture(autouse=True)
@pytest.mark.anyio
async def create_superuser(session):
    data = {
        "id": ADMIN_USER_ID,
        "username": "admin",
        "email": "admin@almalinux.com",
        "is_superuser": True,
        "is_verified": True,
    }
    user = await (
        session.execute(
            select(models.User).where(models.User.id == data["id"]),
        )
    )
    if user.scalars().first():
        return
    await session.execute(insert(models.User).values(**data))
    await session.commit()


@pytest.fixture
@pytest.mark.anyio
async def create_base_platform(session):
    with open("reference_data/platforms.yaml", "rt") as file:
        loader = yaml.Loader(file)
        platform_data = loader.get_data()[0]
    schema = platform_schema.PlatformCreate(**platform_data).dict()
    schema["repos"] = []
    platform = models.Platform(**schema)
    for repo in platform_data.get("repositories", []):
        repo["url"] = repo["remote_url"]
        repository = models.Repository(
            **repository_schema.RepositoryCreate(**repo).dict()
        )
        platform.repos.append(repository)
    session.add(platform)
    await session.commit()


@pytest.fixture(autouse=True)
def mock_create_repo(monkeypatch):
    async def func():
        repo_url = "mock_url"
        repo_href = "mock_href"
        return repo_url, repo_href

    monkeypatch.setattr(PulpClient, "create_rpm_repository", func)

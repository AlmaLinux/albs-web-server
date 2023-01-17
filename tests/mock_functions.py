from contextlib import asynccontextmanager

from sqlalchemy import insert, select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.pool import NullPool
import yaml

from alws import models
from alws.schemas import (
    repository_schema,
    platform_schema,
)
from alws.utils.pulp_client import PulpClient
from alws.config import settings
from tests.constants import ADMIN_USER_ID

engine = create_async_engine(
    settings.test_database_url,
    poolclass=NullPool,
    echo_pool=True,
)


async def get_session():
    async with AsyncSession(engine) as session:
        try:
            yield session
        finally:
            await session.close()


async def create_superuser():
    data = {
        "id": ADMIN_USER_ID,
        "username": "admin",
        "email": "admin@almalinux.com",
        "is_superuser": True,
        "is_verified": True,
    }
    async with asynccontextmanager(get_session)() as session:
        user = await (
            session.execute(
                select(models.User).where(models.User.id == data["id"]),
            )
        )
        if user.scalars().first():
            return
        await session.execute(insert(models.User).values(**data))
        await session.commit()


async def create_base_platform():
    with open("reference_data/platforms.yaml", "rt") as file:
        loader = yaml.Loader(file)
        platform_data = loader.get_data()[0]
    async with asynccontextmanager(get_session)() as session:
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


def mock_create_repo():
    async def func(*args, **kwargs):
        repo_url = "mock_url"
        repo_href = "mock_href"
        return repo_url, repo_href

    return PulpClient, "create_rpm_repository", func

from contextlib import asynccontextmanager
import unittest
import yaml

from fastapi.testclient import TestClient
from sqlalchemy import insert, select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.pool import NullPool
import pytest
import httpx

from alws import models
from alws.app import app
from alws.config import settings
from alws.database import Base
from alws.dependencies import get_db
from alws.schemas import (
    repository_schema,
    platform_schema,
)
from alws.utils import jwt_utils
from alws.utils.pulp_client import PulpClient


@pytest.mark.anyio
class BaseAsyncTestCase(unittest.IsolatedAsyncioTestCase):
    engine = create_async_engine(
        settings.test_database_url,
        poolclass=NullPool,
        echo_pool=True,
    )
    user_id = 1
    token = jwt_utils.generate_JWT_token(
        str(user_id),
        settings.jwt_secret,
        "HS256",
    )
    headers = {"Authorization": f"Bearer {token}"}

    async def get_session(self):
        async with AsyncSession(self.engine) as session:
            try:
                yield session
            finally:
                await session.close()

    async def make_request(
        self,
        method: str,
        endpoint: str,
        headers: dict = None,
        json: dict = None,
    ):
        if not headers:
            headers = {}
        headers.update(self.headers)
        async with httpx.AsyncClient(
            app=app,
            base_url="http://localhost:8080",
        ) as client:
            http_method = getattr(client, method)
            return await http_method(
                endpoint,
                headers=headers,
                json=json,
            )

    @pytest.fixture(autouse=True)
    def mock_create_repo(self, monkeypatch):
        async def func(*args, **kwargs):
            repo_url = 'mock_url'
            repo_href = 'mock_href'
            return repo_url, repo_href

        monkeypatch.setattr(PulpClient, "create_rpm_repository", func)

    async def create_superuser(self):
        data = {
            "id": self.user_id,
            "username": "admin",
            "email": "admin@almalinux.com",
            "is_superuser": True,
            "is_verified": True,
        }
        async with asynccontextmanager(self.get_session)() as session:
            user = await (
                session.execute(
                    select(models.User).where(models.User.id == data["id"]),
                )
            )
            if user.scalars().first():
                return
            await session.execute(insert(models.User).values(**data))
            await session.commit()

    async def create_base_platform(self):
        with open("reference_data/platforms.yaml", "rt") as file:
            loader = yaml.Loader(file)
            platform_data = loader.get_data()[0]
        async with asynccontextmanager(self.get_session)() as session:
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

    @property
    def setup_functions(self):
        return [
            self.create_superuser,
            self.create_base_platform,
        ]

    async def asyncSetUp(self):
        app.dependency_overrides[get_db] = self.get_session
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        for function in self.setup_functions:
            await function()

    async def asyncTearDown(self):
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.drop_all)
        await self.engine.dispose()

import unittest

from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.pool import NullPool
import pytest

from alws.app import app
from alws.database import Base
from alws.dependencies import get_db
from alws.config import settings
from alws.utils import jwt_utils


class BaseAsyncTestCase(unittest.IsolatedAsyncioTestCase):
    client = TestClient(app)
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

    async def asyncSetUp(self):
        app.dependency_overrides[get_db] = self.get_session
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

    async def asyncTearDown(self):
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.drop_all)
        await self.engine.dispose()

    async def get_session(self):
        async with AsyncSession(self.engine) as session:
            try:
                yield session
            finally:
                await session.close()

    def make_request(
        self,
        method: str,
        endpoint: str,
        headers: dict = None,
        json: dict = None,
    ):
        http_method = getattr(self.client, method)
        if not headers:
            headers = {}
        headers.update(self.headers)
        return http_method(
            endpoint,
            headers=headers,
            json=json,
        )

    # @pytest.fixture(autouse=True)
    # def dummy_pulp(self, monkeypatch, *args, **kwargs):
    #     return

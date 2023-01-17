import unittest

import pytest
import httpx

from alws.app import app
from alws.config import settings
from alws.database import Base
from alws.dependencies import get_db
from alws.utils import jwt_utils
from tests.constants import ADMIN_USER_ID
from tests.mock_functions import engine, get_session, create_superuser


@pytest.mark.anyio
class BaseAsyncTestCase(unittest.IsolatedAsyncioTestCase):
    user_id = ADMIN_USER_ID
    token = None
    headers = {}
    monkeypatch = pytest.MonkeyPatch()
    setup_functions = [create_superuser]
    setattr_monkeypatchs = []
    engine = engine

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

    def init_user_credentials(self):
        self.token = jwt_utils.generate_JWT_token(
            str(self.user_id),
            settings.jwt_secret,
            "HS256",
        )
        self.headers.update(
            {
                "Authorization": f"Bearer {self.token}",
            }
        )

    async def execute_setup_functions(self):
        for function in self.setup_functions:
            await function()

    def execute_setattr_monkeypatchs(self):
        for func in self.setattr_monkeypatchs:
            self.monkeypatch.setattr(*func())

    async def asyncSetUp(self):
        app.dependency_overrides[get_db] = get_session
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        await self.execute_setup_functions()
        self.init_user_credentials()
        self.execute_setattr_monkeypatchs()

    async def asyncTearDown(self):
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.drop_all)
        await self.engine.dispose()
        self.monkeypatch.undo()

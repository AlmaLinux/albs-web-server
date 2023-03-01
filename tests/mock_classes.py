import typing
from urllib.parse import urljoin

from fastapi import status
import pytest
import httpx

from alws.app import app
from alws.config import settings
from alws.dependencies import get_db
from alws.utils import jwt_utils

from tests.constants import ADMIN_USER_ID
from tests.fixtures.database import get_session


@pytest.mark.anyio
class BaseAsyncTestCase:
    user_id: int = ADMIN_USER_ID
    token: str = ""
    headers: dict = {}
    status_codes = status

    async def make_request(
        self,
        method: str,
        endpoint: str,
        headers: typing.Optional[dict] = None,
        json: typing.Optional[dict] = None,
        files: typing.Optional[dict] = None,
        data: typing.Optional[dict] = None,
        base_url: str = "http://localhost:8080",
    ) -> httpx.Response:
        if not headers:
            headers = {}
        headers.update(self.headers)
        request = httpx.Request(
            method=method,
            url=urljoin(base_url, endpoint),
            headers=headers,
            json=json,
            data=data,
            files=files,
        )
        async with httpx.AsyncClient(
            app=app,
        ) as client:
            return await client.send(request)

    @classmethod
    def setup_class(cls):
        app.dependency_overrides[get_db] = get_session
        cls.token = jwt_utils.generate_JWT_token(
            str(cls.user_id),
            settings.jwt_secret,
            "HS256",
        )
        cls.headers.update(
            {
                "Authorization": f"Bearer {cls.token}",
            }
        )

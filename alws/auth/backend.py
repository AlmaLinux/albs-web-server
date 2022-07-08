from typing import Any

from fastapi import Response, status
from fastapi_users.authentication import (
    AuthenticationBackend,
    CookieTransport,
)
from .dependencies import get_jwt_strategy


__all__ = [
    'CookieBackend',
]


class RedirectCookieTransport(CookieTransport):
    async def get_login_response(self, token: str, response: Response) -> Any:
        await super().get_login_response(token, response)
        response.status_code = status.HTTP_302_FOUND
        response.headers['Location'] = 'http://localhost:8080/auth/login/github'


cookie_transport = RedirectCookieTransport(
    cookie_max_age=86400, cookie_name='albs')


CookieBackend = AuthenticationBackend(
    name='cookie',
    transport=cookie_transport,
    get_strategy=get_jwt_strategy,
)

from urllib.parse import urljoin, urlparse
from typing import Any

from fastapi import Request, Response, status
from fastapi.security import HTTPBearer
from fastapi_users.authentication import (
    CookieTransport,
    Transport,
)
from fastapi_users.authentication.transport import TransportLogoutNotSupportedError
from fastapi_users.authentication.transport.bearer import BearerResponse
from fastapi_users.openapi import OpenAPIResponseType

from alws.config import settings


__all__ = [
    'get_cookie_transport',
    'get_jwt_transport',
]


class JWTBearer(HTTPBearer):
    async def __call__(self, request: Request):
        # fastapi-users architecture requires the authorization schema
        # to return only token while HTTPBearer class returns an object
        # with the token and schema name. We catch that response and get
        # only token from it for further work.
        creds = await super().__call__(request)
        return creds.credentials


class JWTransport(Transport):
    def __init__(self):
        self.scheme = JWTBearer()

    def get_login_response(self, token: str, response: Response) -> Any:
        return BearerResponse(access_token=token, token_type='bearer')

    async def get_logout_response(self, response: Response) -> Any:
        raise TransportLogoutNotSupportedError()

    @staticmethod
    def get_openapi_login_responses_success() -> OpenAPIResponseType:
        return {
            status.HTTP_200_OK: {
                "model": BearerResponse,
                "content": {
                    "application/json": {
                        "example": {
                            "access_token": "eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9.eyJ1"
                            "c2VyX2lkIjoiOTIyMWZmYzktNjQwZi00MzcyLTg2Z"
                            "DMtY2U2NDJjYmE1NjAzIiwiYXVkIjoiZmFzdGFwaS"
                            "11c2VyczphdXRoIiwiZXhwIjoxNTcxNTA0MTkzfQ."
                            "M10bjOe45I5Ncu_uXvOmVV8QxnL-nZfcH96U90JaocI",
                            "token_type": "bearer",
                        }
                    }
                },
            },
        }

    @staticmethod
    def get_openapi_logout_responses_success() -> OpenAPIResponseType:
        return {}


class RedirectCookieTransport(CookieTransport):
    async def get_login_response(self, token: str, response: Response) -> Any:
        redirect_url = urljoin(settings.frontend_baseurl, 'auth/login/github')
        await super().get_login_response(token, response)
        response.status_code = status.HTTP_302_FOUND
        response.headers['Location'] = redirect_url


def get_cookie_transport(
        cookie_max_age: int = 86400, cookie_name: str = 'albs'):
    cookie_secure = True
    cookie_httponly = True
    parsed_url = urlparse(settings.frontend_baseurl)
    if parsed_url.scheme == 'http':
        cookie_secure = False
    if 'localhost' in parsed_url.netloc:
        cookie_httponly = False

    return RedirectCookieTransport(
        cookie_max_age=cookie_max_age,
        cookie_name=cookie_name,
        cookie_secure=cookie_secure,
        cookie_httponly=cookie_httponly,
    )


def get_jwt_transport() -> JWTransport:
    return JWTransport()

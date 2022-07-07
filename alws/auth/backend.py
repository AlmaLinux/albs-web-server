from typing import Any

from fastapi import Response, status
from fastapi.security import HTTPBearer
from fastapi_users.authentication import (
    AuthenticationBackend,
    BearerTransport,
    CookieTransport,
)
from fastapi_users.authentication.transport.base import (
    Transport,
    TransportLogoutNotSupportedError,
)
from fastapi_users.authentication.transport.bearer import BearerResponse
from fastapi_users.openapi import OpenAPIResponseType

from .dependencies import get_database_strategy, get_jwt_strategy


__all__ = [
    'CookieBackend',
    'JWTBackend',
]


class SimpleBearerTransport(Transport):

    def __init__(self):
        self.scheme = HTTPBearer()

    async def get_login_response(self, token: str, response: Response) -> Any:
        print(token)
        return BearerResponse(access_token=token, token_type="bearer")

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


bearer_transport = BearerTransport(tokenUrl='api/v1/auth/jwt/login')
# bearer_transport = SimpleBearerTransport()
cookie_transport = CookieTransport(cookie_max_age=86400)


JWTBackend = AuthenticationBackend(
    name='jwt',
    transport=bearer_transport,
    get_strategy=get_jwt_strategy,
)
CookieBackend = AuthenticationBackend(
    name='cookie',
    transport=cookie_transport,
    get_strategy=get_database_strategy,
)

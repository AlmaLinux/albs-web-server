from fastapi_users.authentication import AuthenticationBackend

from alws.auth.dependencies import get_jwt_strategy
from alws.auth.transport import get_cookie_transport, get_jwt_transport


__all__ = [
    'CookieBackend',
    'JWTBackend',
]


CookieBackend = AuthenticationBackend(
    name='cookie',
    transport=get_cookie_transport(),
    get_strategy=get_jwt_strategy,
)

JWTBackend = AuthenticationBackend(
    name='jwt',
    transport=get_jwt_transport(),
    get_strategy=get_jwt_strategy,
)

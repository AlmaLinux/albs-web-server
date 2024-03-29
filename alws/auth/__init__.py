from fastapi_users import FastAPIUsers

from alws.auth.backend import CookieBackend, JWTBackend, BearerBackend
from alws.auth.user_manager import get_user_manager


__all__ = [
    'AuthRoutes',
    'get_current_superuser',
    'get_current_user',
]


AuthRoutes = FastAPIUsers(
    get_user_manager=get_user_manager,
    auth_backends=(JWTBackend, CookieBackend, BearerBackend)
)

get_current_user = AuthRoutes.current_user(active=True, verified=True)
get_current_superuser = AuthRoutes.current_user(
    active=True, verified=True, superuser=True)

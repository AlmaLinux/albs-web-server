import logging
import time
import typing

from fastapi import Depends, HTTPException, status
from fastapi_users import FastAPIUsers

from alws.auth.backend import CookieBackend, JWTBackend, BearerBackend
from alws.auth.user_manager import get_user_manager
from alws.models import User


__all__ = [
    'AuthRoutes',
    'check_build_node_name',
    'get_current_build_node',
    'get_current_superuser',
    'get_current_user',
]

# How often to warn that a build node uses the token of a superuser
SUPERUSER_NODE_WARNING_INTERVAL = 600


AuthRoutes = FastAPIUsers(
    get_user_manager=get_user_manager,
    auth_backends=(JWTBackend, CookieBackend, BearerBackend)
)

_current_user = AuthRoutes.current_user(active=True, verified=True)
_current_superuser = AuthRoutes.current_user(
    active=True, verified=True, superuser=True)
# The last warnings about the superuser tokens of the nodes, by user id
_superuser_node_warnings: typing.Dict[int, float] = {}


def _reject_build_node(user: User):
    # The token of a build node is good for /build_node/* only,
    # whatever else the user is
    if user.is_build_node:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail='The token of a build node gives access to '
            '/build_node/* only',
        )


async def get_current_user(user: User = Depends(_current_user)) -> User:
    _reject_build_node(user)
    return user


async def get_current_superuser(
    user: User = Depends(_current_superuser),
) -> User:
    _reject_build_node(user)
    return user


def _warn_superuser_node(user: User):
    now = time.monotonic()
    last = _superuser_node_warnings.get(user.id)
    if last is not None and now - last < SUPERUSER_NODE_WARNING_INTERVAL:
        return
    _superuser_node_warnings[user.id] = now
    logging.warning(
        'A build node uses the token of superuser %s (id %d). Issue '
        'a build node token with scripts/build_node_token.py and replace '
        'it, a superuser token gives the node full access to the API',
        user.username or user.email,
        user.id,
    )


async def get_current_build_node(
    user: User = Depends(_current_user),
) -> User:
    """The user of the build node calling /build_node/*.

    Superusers are accepted too, as the nodes deployed before the build
    node users have the token of a superuser.
    """
    if user.is_build_node:
        return user
    if user.is_superuser:
        _warn_superuser_node(user)
        return user
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail='Only build nodes can use this endpoint',
    )


def check_build_node_name(user: User, node_name: typing.Optional[str]):
    """Reject a token bound to a node used for another node."""
    if not user.is_build_node or not user.build_node_name:
        return
    if node_name != user.build_node_name:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f'The token is bound to build node '
            f'{user.build_node_name}',
        )

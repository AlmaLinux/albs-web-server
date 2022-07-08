from fastapi import Depends
from fastapi_users.db import SQLAlchemyUserDatabase
from fastapi_users.manager import BaseUserManager, IntegerIDMixin
from alws.config import settings
from .dependencies import get_user_db

__all__ = [
    'get_user_manager',
    'UserManager',
]


class UserManager(IntegerIDMixin, BaseUserManager):
    reset_password_token_secret = settings.jwt_secret
    verification_token_secret = settings.jwt_secret


async def get_user_manager(
        user_db: SQLAlchemyUserDatabase = Depends(get_user_db)
) -> UserManager:
    yield UserManager(user_db)

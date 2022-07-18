import logging
import uuid
from typing import Optional

from fastapi import Depends, Request
from fastapi_users import BaseUserManager, UUIDIDMixin

from alws.models import User, get_user_db

SECRET = "a2a2m6d3g4P&"


class UserManager(UUIDIDMixin, BaseUserManager[User, uuid.UUID]):
    reset_password_token_secret = SECRET
    verification_token_secret = SECRET

    async def on_after_register(
            self,
            user: User,
            request: Optional[Request] = None,
    ):
        logging.info('User "%s" has registered.', user.id)

    async def on_after_forgot_password(
            self,
            user: User,
            token: str,
            request: Optional[Request] = None,
    ):
        logging.info(
            'User "%s" has forgot their password. Reset token: %s',
            user.id,
            token,
        )

    async def on_after_request_verify(
            self,
            user: User,
            token: str,
            request: Optional[Request] = None,
    ):
        logging.info(
            'Verification requested for user "%s". Verification token: %s',
            user.id,
            token,
        )


async def get_user_manager(user_db=Depends(get_user_db)):
    yield UserManager(user_db)

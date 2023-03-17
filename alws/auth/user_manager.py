from typing import Optional

from fastapi import Depends, Request
from fastapi_users import models
from fastapi_users.db import SQLAlchemyUserDatabase
from fastapi_users.manager import BaseUserManager, IntegerIDMixin
from alws.config import settings
from alws.utils.github import get_github_user_info
from .dependencies import get_user_db

__all__ = [
    'get_user_manager',
    'UserManager',
]


class UserManager(IntegerIDMixin, BaseUserManager):
    reset_password_token_secret = settings.jwt_secret
    verification_token_secret = settings.jwt_secret

    async def oauth_callback(
        self: "BaseUserManager[models.UOAP, models.ID]",
        oauth_name: str,
        access_token: str,
        account_id: str,
        account_email: str,
        expires_at: Optional[int] = None,
        refresh_token: Optional[str] = None,
        request: Optional[Request] = None,
        *,
        associate_by_email: bool = False,
        is_verified_by_default: bool = False,
    ) -> models.UOAP:
        user = await super().oauth_callback(
            oauth_name, access_token, account_id, account_email,
            expires_at=expires_at, refresh_token=refresh_token,
            request=request, associate_by_email=associate_by_email,
            is_verified_by_default=is_verified_by_default,
        )
        token = None
        for existing_oauth_account in user.oauth_accounts:
            if (
                existing_oauth_account.account_id == account_id
                and existing_oauth_account.oauth_name == oauth_name
            ):
                token = existing_oauth_account.access_token
        try:
            user_info = await get_github_user_info(token)
            update_dict = {'username': user_info['login']}
            await self.user_db.update(user, update_dict)
        except Exception:
            username = user.email.split('@')[0]
            update_dict = {'username': username}
            await self.user_db.update(user, update_dict)
        return user


async def get_user_manager(
        user_db: SQLAlchemyUserDatabase = Depends(get_user_db)
) -> UserManager:
    yield UserManager(user_db)

import typing

from fastapi_users.schemas import (
    BaseUser,
    BaseUserCreate,
    BaseUserUpdate,
)


__all__ = [
    'UserCreate',
    'UserRead',
    'UserUpdate',
]


class UserRead(BaseUser):
    username: str
    first_name: typing.Optional[str] = None
    last_name: typing.Optional[str] = None


class UserCreate(BaseUserCreate):
    username: str
    first_name: typing.Optional[str]
    last_name: typing.Optional[str]


class UserUpdate(BaseUserUpdate):
    username: typing.Optional[str]
    first_name: typing.Optional[str]
    last_name: typing.Optional[str]

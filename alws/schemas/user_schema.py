import typing

from pydantic import BaseModel

__all__ = ['User', 'LoginGithub', 'UserOpResult']


class LoginGithub(BaseModel):
    code: str


class User(BaseModel):
    id: int
    username: str
    email: str
    is_active: bool
    is_superuser: bool

    class Config:
        from_attributes = True


class UserUpdate(BaseModel):
    id: int
    is_active: typing.Optional[bool] = None
    is_verified: typing.Optional[bool] = None
    is_superuser: typing.Optional[bool] = None


class UserOpResult(BaseModel):
    success: bool
    message: typing.Optional[str] = None


class UserTeam(BaseModel):
    id: int
    name: str

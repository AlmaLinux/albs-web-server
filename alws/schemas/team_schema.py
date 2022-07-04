import typing

from pydantic import BaseModel

from alws.schemas.user_schema import User
from alws.schemas.role_schema import Role


__all__ = ['Team']


class Team(BaseModel):
    id: int
    name: str
    members: typing.Optional[typing.List[User]]
    owner: typing.Optional[User]
    roles: typing.Optional[typing.List[Role]]

    class Config:
        orm_mode = True

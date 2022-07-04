import typing

from pydantic import BaseModel

from alws.schemas.user_schema import User
from alws.schemas.team_schema import Team


__all__ = ['ProductCreate']


class ProductCreate(BaseModel):
    name: str
    team_id: int
    owner_id: int


class Product(BaseModel):
    id: int
    name: str
    owner: typing.Optional[User]
    team: typing.Optional[Team]

    class Config:
        orm_mode = True

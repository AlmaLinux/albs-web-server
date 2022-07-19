import typing

from pydantic import BaseModel

from alws.schemas.platform_schema import Platform
from alws.schemas.repository_schema import Repository
from alws.schemas.team_schema import Team
from alws.schemas.user_schema import User

__all__ = ['ProductCreate']


class ProductCreate(BaseModel):
    name: str
    team_id: int
    owner_id: int
    platforms: typing.List[Platform] = []


class ProductBuild(BaseModel):
    id: int

    class Config:
        orm_mode = True


class Product(BaseModel):
    id: int
    name: str
    builds: typing.Optional[typing.List[ProductBuild]] = []
    repositories: typing.Optional[typing.List[Repository]] = []
    owner: typing.Optional[User]
    team: typing.Optional[Team]

    class Config:
        orm_mode = True

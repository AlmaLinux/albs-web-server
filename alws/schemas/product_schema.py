import typing

from pydantic import BaseModel

from alws.schemas.platform_schema import Platform
from alws.schemas.repository_schema import Repository
from alws.schemas.team_schema import Team
from alws.schemas.user_schema import User

__all__ = ['ProductCreate', 'Product']


class ProductCreate(BaseModel):
    name: str
    owner_id: int
    title: str
    description: typing.Optional[str]
    platforms: typing.List[Platform] = []
    is_community: bool = True


class ProductBuild(BaseModel):
    id: int

    class Config:
        orm_mode = True


class Product(BaseModel):
    id: int
    name: str
    title: typing.Optional[str]
    description: typing.Optional[str]
    builds: typing.List[ProductBuild] = []
    repositories: typing.List[Repository] = []
    platforms: typing.List[Platform] = []
    owner: User
    team: Team
    is_community: bool

    class Config:
        orm_mode = True


class ProductResponse(BaseModel):
    products: typing.List[Product]
    total_products: typing.Optional[int]
    current_page: typing.Optional[int]

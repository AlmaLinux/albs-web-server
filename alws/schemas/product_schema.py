import typing

from alws.schemas.platform_schema import Platform
from alws.schemas.repository_schema import Repository
from alws.schemas.team_schema import Team
from alws.schemas.user_schema import User
from pydantic import BaseModel

__all__ = ['ProductCreate', 'Product', 'ProductOpResult']


class ProductCreate(BaseModel):
    name: str
    owner_id: int
    title: str
    description: typing.Optional[str] = None
    platforms: typing.List[Platform] = []
    is_community: bool = True


class ProductBuild(BaseModel):
    id: int

    class Config:
        from_attributes = True


class Product(BaseModel):
    id: int
    name: str
    title: typing.Optional[str] = None
    description: typing.Optional[str] = None
    builds: typing.List[ProductBuild] = []
    repositories: typing.List[Repository] = []
    platforms: typing.List[Platform] = []
    owner: User
    team: Team
    is_community: bool

    class Config:
        from_attributes = True


class ProductResponse(BaseModel):
    products: typing.List[Product]
    total_products: typing.Optional[int] = None
    current_page: typing.Optional[int] = None


class ProductOpResult(BaseModel):

    success: bool
    message: typing.Optional[str] = None

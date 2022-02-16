import typing

from pydantic import BaseModel


__all__ = ['Repository', 'RepositoryCreate', 'RepositoryUpdate',
           'RepositorySearch', 'RepositorySync']


class Repository(BaseModel):
    id: int
    name: str
    arch: str
    url: str
    type: str
    debug: typing.Optional[bool]
    production: typing.Optional[bool]
    pulp_href: typing.Optional[str]

    class Config:
        orm_mode = True


class RepositoryModify(BaseModel):
    name: typing.Optional[str] = None
    arch: typing.Optional[str] = None
    url: typing.Optional[str] = None
    type: typing.Optional[str] = None
    debug: typing.Optional[str] = None
    production: typing.Optional[bool] = False
    pulp_href: typing.Optional[str] = None
    remote_url: typing.Optional[str] = None


class RepositoryCreate(BaseModel):
    name: str
    arch: str
    url: str
    type: str
    debug: bool
    production: bool = False
    pulp_href: typing.Optional[str]
    remote_url: typing.Optional[str]


class RepositorySearch(BaseModel):
    name: typing.Optional[str]
    arch: typing.Optional[str]
    url: typing.Optional[str]
    type: typing.Optional[str]
    debug: typing.Optional[bool]
    production: typing.Optional[bool]
    pulp_href: typing.Optional[str]


class RepositoryUpdate(BaseModel):
    name: typing.Optional[str]
    arch: typing.Optional[str]
    url: typing.Optional[str]
    type: typing.Optional[str]
    debug: typing.Optional[bool]
    production: typing.Optional[bool]


class RepositorySync(BaseModel):
    remote_id: int
    sync_policy: str = 'additive'

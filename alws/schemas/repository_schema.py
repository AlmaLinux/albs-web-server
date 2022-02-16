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


class RepositoryCreate(BaseModel):
    name: str
    arch: str
    url: str
    type: str
    debug: bool
    production: bool = False
    pulp_href: typing.Optional[str]


class RepositorySearch(BaseModel):
    name: typing.Optional[str]
    arch: typing.Optional[str]
    url: typing.Optional[str]
    type: typing.Optional[str]
    debug: typing.Optional[bool]
    production: typing.Optional[bool]
    pulp_href: typing.Optional[str]


class RepositoryUpdate(BaseModel):
    production: typing.Optional[bool]
    export_path: typing.Optional[str]


class RepositorySync(BaseModel):
    remote_id: int
    sync_policy: str = 'additive'

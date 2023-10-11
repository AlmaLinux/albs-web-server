import typing

from pydantic import BaseModel


__all__ = [
    'Repository',
    'RepositoryCreate',
    'RepositoryUpdate',
    'RepositorySearch',
    'RepositorySync',
]


class Repository(BaseModel):
    id: int
    name: str
    arch: str
    url: str
    type: str
    debug: typing.Optional[bool]
    priority: typing.Optional[int]
    production: typing.Optional[bool]
    mock_enabled: typing.Optional[bool]
    pulp_href: typing.Optional[str]

    class Config:
        orm_mode = True


class RepositoryCreate(BaseModel):
    name: str
    arch: str
    url: str
    type: str
    debug: bool
    priority: int = 10
    production: bool = False
    mock_enabled: bool = True
    export_path: typing.Optional[str]
    pulp_href: typing.Optional[str]


class RepositorySearch(BaseModel):
    name: typing.Optional[str]
    arch: typing.Optional[str]
    url: typing.Optional[str]
    type: typing.Optional[str]
    debug: typing.Optional[bool]
    production: typing.Optional[bool]
    pulp_href: typing.Optional[str]
    mock_enabled: typing.Optional[bool]


class RepositoryUpdate(BaseModel):
    priority: int = 10
    production: typing.Optional[bool]
    export_path: typing.Optional[str]
    pulp_href: typing.Optional[str]
    mock_enabled: bool = True


class RepositorySync(BaseModel):
    remote_id: int
    sync_policy: str = 'additive'

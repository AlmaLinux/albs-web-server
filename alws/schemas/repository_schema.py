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
    debug: typing.Optional[bool] = None
    priority: typing.Optional[int] = None
    production: typing.Optional[bool] = None
    mock_enabled: typing.Optional[bool] = None
    pulp_href: typing.Optional[str] = None

    class Config:
        from_attributes = True


class RepositoryCreate(BaseModel):
    name: str
    arch: str
    url: str
    type: str
    debug: bool
    priority: int = 10
    production: bool = False
    mock_enabled: bool = True
    owner_id: typing.Optional[int] = None
    export_path: typing.Optional[str] = None
    pulp_href: typing.Optional[str] = None


class RepositorySearch(BaseModel):
    name: typing.Optional[str] = None
    arch: typing.Optional[str] = None
    url: typing.Optional[str] = None
    type: typing.Optional[str] = None
    debug: typing.Optional[bool] = None
    production: typing.Optional[bool] = None
    pulp_href: typing.Optional[str] = None
    mock_enabled: typing.Optional[bool] = None


class RepositoryUpdate(BaseModel):
    priority: int = 10
    production: typing.Optional[bool] = None
    export_path: typing.Optional[str] = None
    pulp_href: typing.Optional[str] = None
    mock_enabled: bool = True


class RepositorySync(BaseModel):
    remote_id: int
    sync_policy: str = 'additive'

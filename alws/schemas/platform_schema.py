import typing

from pydantic import BaseModel

from alws.schemas.repository_schema import RepositoryCreate


__all__ = ['PlatformCreate', 'Platform']


class PlatformModify(BaseModel):

    name: str
    contact_mail: typing.Optional[str]
    copyright: typing.Optional[str]
    type: typing.Optional[typing.Literal['rpm', 'deb']] = None
    distr_type: typing.Optional[str] = None
    distr_version: typing.Optional[str] = None
    arch_list: typing.Optional[typing.List[str]] = None
    copy_priority_arches: typing.Optional[typing.List[str]] = None
    reference_platforms: typing.Optional[typing.List[str]] = []
    repos: typing.Optional[typing.List[RepositoryCreate]] = []
    data: typing.Optional[typing.Dict[str, typing.Any]] = None
    modularity: typing.Optional[typing.Dict[str, typing.Any]] = None
    is_reference: typing.Optional[bool] = False
    weak_arch_list: typing.Optional[typing.List[typing.Dict]] = None


class PlatformCreate(BaseModel):

    name: str
    contact_mail: typing.Optional[str]
    copyright: typing.Optional[str]
    type: typing.Literal['rpm', 'deb']
    distr_type: str
    distr_version: str
    test_dist_name: typing.Optional[str]
    arch_list: typing.List[str]
    repos: typing.Optional[typing.List[RepositoryCreate]]
    data: typing.Optional[typing.Dict[str, typing.Any]]
    modularity: typing.Optional[typing.Dict[str, typing.Any]] = None
    is_reference: typing.Optional[bool] = False


class Platform(BaseModel):

    id: int
    name: str
    distr_type: str
    distr_version: str

    arch_list: typing.List[str]
    modularity: typing.Optional[typing.Dict]

    class Config:
        orm_mode = True

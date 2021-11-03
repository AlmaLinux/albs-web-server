import typing

from pydantic import BaseModel


__all__ = ['PlatformCreate', 'Platform']


class PlatformRepo(BaseModel):

    name: str
    arch: str
    url: str
    type: str
    production: bool = False


class PlatformModify(BaseModel):

    name: str
    type: typing.Optional[typing.Literal['rpm', 'deb']] = None
    distr_type: typing.Optional[str] = None
    distr_version: typing.Optional[str] = None
    arch_list: typing.Optional[typing.List[str]] = None
    repos: typing.Optional[typing.List[PlatformRepo]] = None
    data: typing.Optional[typing.Dict[str, typing.Any]] = None


class PlatformCreate(BaseModel):

    name: str
    type: typing.Literal['rpm', 'deb']
    distr_type: str
    distr_version: str
    test_dist_name: str
    arch_list: typing.List[str]
    repos: typing.List[PlatformRepo]
    data: typing.Dict[str, typing.Any]


class Platform(BaseModel):

    id: int
    name: str

    arch_list: typing.List[str]

    class Config:
        orm_mode = True

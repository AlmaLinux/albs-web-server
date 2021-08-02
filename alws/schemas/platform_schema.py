import typing

from pydantic import BaseModel


__all__ = ['PlatformCreate', 'Platform']


class PlatformRepo(BaseModel):

    name: str
    arch: str
    url: str
    type: str


class PlatformCreate(BaseModel):

    name: str
    type: typing.Literal['rpm', 'deb']
    distr_type: str
    distr_version: str
    arch_list: typing.List[str]
    repos: typing.List[PlatformRepo]
    data: typing.Dict[str, typing.Any]


class Platform(BaseModel):

    id: int
    name: str

    arch_list: typing.List[str]

    class Config:
        orm_mode = True

import typing
import datetime

from pydantic import BaseModel


__all__ = ['Distribution', 'DistroCreate']


class DistroRepository(BaseModel):

    id: int
    name: str
    arch: str
    url: str
    type: str
    pulp_href: str


class DistroPlatforms(BaseModel):

    id: int
    type: typing.Optional[str]
    distr_type: typing.Optional[str]
    distr_version: typing.Optional[str]
    name: str
    arch_list: typing.List[str]
    data: typing.Optional[typing.Any]
    repos: typing.Optional[typing.Any]


class DistroCreate(BaseModel):

    name: str
    platforms: typing.List[str]


class Distribution(BaseModel):

    id: int
    name: str

    class Config:
        orm_mode = True

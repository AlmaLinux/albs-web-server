import typing

from pydantic import BaseModel


__all__ = ['Remote', 'RemoteCreate', 'RemoteUpdate']


class Remote(BaseModel):
    name: str
    arch: str
    url: str

    class Config:
        orm_mode = True


class RemoteCreate(BaseModel):
    name: str
    arch: str
    url: str
    policy: str = 'on_demand'


class RemoteUpdate(BaseModel):
    name: typing.Optional[str]
    arch: typing.Optional[str]
    url: typing.Optional[str]

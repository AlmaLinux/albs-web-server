import typing

from pydantic import BaseModel

__all__ = ['Remote', 'RemoteCreate', 'RemoteUpdate']


class Remote(BaseModel):
    name: str
    arch: str
    url: str

    class Config:
        from_attributes = True


class RemoteCreate(BaseModel):
    name: str
    arch: str
    url: str
    policy: str = 'on_demand'
    proxy_url: typing.Optional[str] = None
    proxy_username: typing.Optional[str] = None
    proxy_password: typing.Optional[str] = None


class RemoteUpdate(BaseModel):
    name: typing.Optional[str] = None
    arch: typing.Optional[str] = None
    url: typing.Optional[str] = None
    pulp_href: typing.Optional[str] = None

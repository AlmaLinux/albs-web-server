import typing

from pydantic import BaseModel

__all__ = ['FileSystemExporter']


class FileSystemExporter(BaseModel):
    pulp_href: typing.Optional[str] = None
    pulp_created: typing.Optional[str] = None
    name: typing.Optional[str] = None
    path: typing.Optional[str] = None
    method: typing.Optional[str] = None

import typing

from pydantic import BaseModel


__all__ = ['FileSystemExporter']

class FileSystemExporter(BaseModel):
    pulp_href: typing.Optional[str]
    pulp_created: typing.Optional[str]
    name: typing.Optional[str]
    path: typing.Optional[str]
    method: typing.Optional[str]

import typing

from pydantic import BaseModel

from alws.schemas.repository_schema import Repository

__all__ = ['CoprDistribution']


class CoprDistribution(BaseModel):
    name: str
    full_name: str
    description: str
    ownername: str
    chroot_repos: typing.List[Repository]

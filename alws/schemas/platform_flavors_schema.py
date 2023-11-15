import typing

from alws.schemas.repository_schema import Repository, RepositoryCreate
from pydantic import BaseModel


class CreateFlavour(BaseModel):

    name: str
    modularity: typing.Optional[dict] = None
    repositories: typing.List[RepositoryCreate]
    data: typing.Optional[typing.Dict[str, typing.Any]] = None


class UpdateFlavour(BaseModel):

    name: str
    modularity: typing.Optional[dict] = None
    repositories: typing.Optional[typing.List[RepositoryCreate]] = None
    data: typing.Optional[typing.Dict[str, typing.Any]] = None


class FlavourResponse(BaseModel):

    id: int
    name: str
    repos: typing.List[Repository]
    modularity: typing.Optional[dict] = None
    data: typing.Optional[typing.Dict[str, typing.Any]] = None

    class Config:
        from_attributes = True

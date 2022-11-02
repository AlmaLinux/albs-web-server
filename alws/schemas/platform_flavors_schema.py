import typing

from pydantic import BaseModel

from alws.schemas.repository_schema import RepositoryCreate, Repository


class CreateFlavour(BaseModel):

    name: str
    modularity: typing.Optional[dict] = None
    repositories: typing.List[RepositoryCreate]
    data: typing.Optional[typing.Dict[str, typing.Any]]


class UpdateFlavour(BaseModel):

    name: str
    modularity: typing.Optional[dict] = None
    repositories: typing.Optional[typing.List[RepositoryCreate]] = None
    data: typing.Optional[typing.Dict[str, typing.Any]] = None


class FlavourResponse(BaseModel):

    id: int
    name: str
    repos: typing.List[Repository]
    modularity: typing.Optional[dict]
    data: typing.Optional[typing.Dict[str, typing.Any]]

    class Config:
        orm_mode = True

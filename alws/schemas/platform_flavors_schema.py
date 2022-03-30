from typing import List

from pydantic import BaseModel

from alws.schemas.repository_schema import RepositoryCreate, Repository


class CreateFlavour(BaseModel):

    name: str
    repositories: List[RepositoryCreate]


class FlavourResponse(BaseModel):

    id: int
    name: str
    repos: List[Repository]

    class Config:
        orm_mode = True
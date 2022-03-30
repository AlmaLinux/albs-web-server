from typing import List

from pydantic import BaseModel

from alws.schemas.repository_schema import RepositoryCreate


class CreateFlavour(BaseModel):

    name: str
    repos: List[RepositoryCreate]


class FlavourResponse(BaseModel):

    id: int
    name: str
    repos: List[RepositoryCreate]

    class Config:
        orm_mode = True
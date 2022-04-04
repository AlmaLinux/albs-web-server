from typing import List, Optional

from pydantic import BaseModel

from alws.schemas.repository_schema import RepositoryCreate, Repository


class CreateFlavour(BaseModel):

    name: str
    modularity: Optional[dict] = None
    repositories: List[RepositoryCreate]


class UpdateFlavour(BaseModel):

    id: int
    name: Optional[str] = None
    modularity: Optional[dict] = None
    repositories: Optional[List[RepositoryCreate]] = None


class FlavourResponse(BaseModel):

    id: int
    name: str
    repos: List[Repository]
    modularity: Optional[dict]

    class Config:
        orm_mode = True
import typing

from pydantic import BaseModel, Field

from alws.schemas.user_schema import User
from alws.schemas.platform_schema import Platform


__all__ = [
    'Release',
    'ReleaseCommitResult',
    'ReleaseCreate',
    'ReleaseUpdate',
]


class Release(BaseModel):
    id: int
    status: int
    build_ids: typing.List[int]
    build_task_ids: typing.Optional[typing.List[int]] = \
        Field(default_factory=list)
    plan: typing.Optional[typing.Dict[str, typing.Any]]
    owner: User
    platform: Platform

    class Config:
        orm_mode = True


class ReleaseResponse(BaseModel):

    releases: typing.List[Release]
    total_releases: typing.Optional[int]
    current_page: typing.Optional[int]


class ReleaseCreate(BaseModel):
    builds: typing.List[int]
    build_tasks: typing.Optional[typing.List[int]]
    platform_id: int


class ReleaseUpdate(BaseModel):
    builds: typing.Optional[typing.List[int]]
    build_tasks: typing.Optional[typing.List[int]]
    plan: typing.Optional[typing.Dict[str, typing.Any]]


class ReleaseCommitResult(BaseModel):
    message: str

import typing

from pydantic import BaseModel

from alws.schemas.user_schema import User


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
    build_tasks_ids: typing.Optional[typing.List[int]]
    plan: typing.Optional[typing.Dict[str, typing.Any]]
    created_by: User

    class Config:
        orm_mode = True


class ReleaseCreate(BaseModel):
    builds: typing.List[int]
    build_tasks: typing.Optional[typing.List[int]]
    platform_id: int
    reference_platform_id: int


class ReleaseUpdate(BaseModel):
    builds: typing.Optional[typing.List[int]]
    build_tasks: typing.Optional[typing.List[int]]
    plan: typing.Optional[typing.Dict[str, typing.Any]]


class ReleaseCommitResult(BaseModel):
    release: Release
    message: str

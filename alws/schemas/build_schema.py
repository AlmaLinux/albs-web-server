import typing
import datetime

from pydantic import BaseModel


__all__ = ['BuildTaskRef', 'BuildCreate', 'Build']


class BuildTaskRef(BaseModel):

    ref_type: typing.Literal['srpm', 'git_tag', 'git_branch']
    url: str
    git_ref: typing.Optional[str]

    class Config:
        orm_mode = True


class BuildCreate(BaseModel):

    platforms: typing.List[str]
    tasks: typing.List[BuildTaskRef]


class BuildPlatform(BaseModel):

    id: int
    type: str
    name: str
    arch_list: typing.List[str]

    class Config:
        orm_mode = True


class BuildTask(BaseModel):

    id: int
    ts: typing.Optional[datetime.datetime]
    status: int
    index: int
    arch: str
    platform: BuildPlatform
    ref: BuildTaskRef

    class Config:
        orm_mode = True


class BuildUser(BaseModel):

    id: int
    username: str
    email: str

    class Config:
        orm_mode = True


class Build(BaseModel):

    id: int
    created_at: datetime.datetime
    tasks: typing.List[BuildTask]
    user: BuildUser

    class Config:
        orm_mode = True

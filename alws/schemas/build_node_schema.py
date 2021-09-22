import re
import typing

from pydantic import BaseModel, Field


__all__ = ['Task']


class TaskRepo(BaseModel):

    name: str
    url: str

    class Config:
        orm_mode = True


class TaskRef(BaseModel):

    url: str
    git_ref: typing.Optional[str]

    class Config:
        orm_mode = True


class TaskCreatedBy(BaseModel):

    name: str
    email: str


class TaskPlatform(BaseModel):

    name: str
    type: typing.Literal['rpm', 'deb']
    data: typing.Dict[str, typing.Any]

    class Config:
        orm_mode = True


class Task(BaseModel):

    id: int
    arch: str
    ref: TaskRef
    platform: TaskPlatform
    created_by: TaskCreatedBy
    repositories: typing.List[TaskRepo]
    linked_builds: typing.Optional[typing.List[int]] = Field(default_factory=list)

    class Config:
        orm_mode = True


class Ping(BaseModel):

    active_tasks: typing.List[int]


class BuildDoneArtifact(BaseModel):

    name: str
    type: typing.Literal['rpm', 'build_log']
    href: str

    @property
    def arch(self):
        # TODO: this is awful way to check pkg arch
        return self.name.split('.')[-2]

    @property
    def is_debuginfo(self):
        return bool(re.search(r'-debug(info|source)', self.name))


class BuildDone(BaseModel):

    task_id: int
    status: typing.Literal['done', 'failed', 'excluded']
    artifacts: typing.List[BuildDoneArtifact]


class RequestTask(BaseModel):

    supported_arches: typing.List[str]

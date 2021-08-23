import typing

from pydantic import BaseModel


__all__ = ['Task']


class TaskRepo(BaseModel):

    name: str
    url: str

    # TODO: remove this
    channel = 0

    class Config:
        orm_mode = True


class TaskRef(BaseModel):

    ref_type: str
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
    linked_builds: typing.Optional[typing.List[int]]

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


class BuildDone(BaseModel):

    task_id: int
    success: bool
    artifacts: typing.List[BuildDoneArtifact]

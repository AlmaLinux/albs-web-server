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

    def add_mock_options(self, options):
        for k, v in options.items():
            if k in ('module_enable', 'target_arch'):
                self.data['mock'][k] = v
            elif k == 'yum_exclude':
                old_exclude = self.data['yum'].get('exclude', '')
                self.data['yum']['exclude'] = f'{old_exclude} {" ".join(v)}'
            elif k in ('with', 'without'):
                for i in v:
                    self.data['definitions'][f'_{k}_{i}'] = f'--{k}-{i}'
            else:
                for v_k, v_v in v.items():
                    self.data['definitions'][v_k] = v_v

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

    class Config:
        orm_mode = True

    @property
    def arch(self):
        # TODO: this is awful way to check pkg arch
        return self.name.split('.')[-2]

    @property
    def is_debuginfo(self):
        regex = re.compile(r'-debug(info|source)-\d')
        return bool(re.search(regex, self.name))


class BuildDone(BaseModel):

    task_id: int
    status: typing.Literal['done', 'failed', 'excluded']
    artifacts: typing.List[BuildDoneArtifact]


class RequestTask(BaseModel):

    supported_arches: typing.List[str]

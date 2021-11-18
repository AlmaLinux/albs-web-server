import typing
import datetime

from pydantic import BaseModel, validator, Field, conlist


__all__ = ['BuildTaskRef', 'BuildCreate', 'Build', 'BuildsResponse']


class BuildTaskRef(BaseModel):

    url: str
    git_ref: typing.Optional[str]
    ref_type: typing.Optional[int]

    @property
    def is_module(self):
        return '/modules/' in self.url

    class Config:
        orm_mode = True


class BuildCreatePlatforms(BaseModel):

    name: str
    arch_list: typing.List[str]


class BuildCreate(BaseModel):

    platforms: conlist(BuildCreatePlatforms, min_items=1)
    tasks: conlist(BuildTaskRef, min_items=1)
    linked_builds: typing.Optional[typing.List[int]]
    mock_options: typing.Optional[typing.Dict[str, typing.Any]]


class BuildPlatform(BaseModel):

    id: int
    type: str
    name: str
    arch_list: typing.List[str]

    class Config:
        orm_mode = True


class BuildTaskArtifact(BaseModel):

    id: int
    name: str
    type: str
    href: str

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
    artifacts: typing.List[BuildTaskArtifact]

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
    linked_builds: typing.Optional[typing.List[int]] = Field(default_factory=list)
    mock_options: typing.Optional[typing.Dict[str, typing.Any]]

    @validator('linked_builds', pre=True)
    def linked_builds_validator(cls, v):
        return [item if isinstance(item, int) else item.id for item in v]

    class Config:
        orm_mode = True


class BuildsResponse(BaseModel):

    builds: typing.List[Build]
    total_builds: typing.Optional[int]
    current_page: typing.Optional[int]

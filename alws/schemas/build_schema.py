import typing
import datetime
import urllib.parse

from pydantic import BaseModel, validator, Field, conlist

from alws.constants import BuildTaskRefType


__all__ = ['BuildTaskRef', 'BuildCreate', 'Build', 'BuildsResponse']


class BuildTaskRef(BaseModel):

    url: str
    git_ref: typing.Optional[str]
    ref_type: typing.Optional[typing.Union[int, str]]
    is_module: typing.Optional[bool] = False
    module_platform_version: typing.Optional[str] = None
    module_version: typing.Optional[str] = None

    @property
    def git_repo_name(self):
        parsed_url = urllib.parse.urlparse(self.url)
        git_name = parsed_url.path.split('/')[-1]
        return git_name.replace('.git', '')

    def module_stream_from_ref(self):
        if 'stream-' in self.git_ref:
            return self.git_ref.split('stream-')[-1]
        return self.git_ref

    @validator('ref_type', pre=True)
    def ref_type_validator(cls, v):
        if v is None:
            return v
        return v if isinstance(v, int) else BuildTaskRefType.from_text(v)

    def ref_type_to_str(self):
        return BuildTaskRefType.to_text(self.ref_type)

    def get_dev_module(self) -> 'BuildTaskRef':
        model_copy = self.copy(deep=True)
        model_copy.url = self.url.replace(
            self.git_repo_name,
            self.git_repo_name + '-devel'
        )
        return model_copy

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
    is_secure_boot: bool


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
    is_secure_boot: typing.Optional[bool]

    class Config:
        orm_mode = True


class BuildSearch(BaseModel):

    created_by: typing.Optional[int]
    project: typing.Optional[str]
    ref: typing.Optional[str]
    rpm_name: typing.Optional[str]
    rpm_epoch: typing.Optional[str]
    rpm_version: typing.Optional[str]
    rpm_release: typing.Optional[str]
    rpm_arch: typing.Optional[str]
    platform_id: typing.Optional[int]
    build_task_arch: typing.Optional[str]
    released: typing.Optional[bool]
    signed: typing.Optional[bool]

    @property
    def is_package_filter(self):
        return any((
            self.rpm_name is not None,
            self.rpm_epoch is not None,
            self.rpm_version is not None,
            self.rpm_release is not None,
            self.rpm_arch is not None,
        ))


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

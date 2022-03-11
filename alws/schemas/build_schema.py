import asyncio
import typing
import logging
import datetime
import urllib.parse

import aiohttp.client_exceptions
from pydantic import BaseModel, validator, Field, conlist

from alws.config import settings
from alws.constants import BuildTaskRefType
from alws.utils.gitea import (
    download_modules_yaml, GiteaClient, ModulesYamlNotFoundError
)
from alws.utils.modularity import ModuleWrapper, get_modified_refs_list


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


class BuildTaskModuleRef(BaseModel):

    module_name: str
    module_stream: str
    module_platform_version: str
    module_version: typing.Optional[str] = None
    modules_yaml: str
    refs: typing.List[BuildTaskRef]


class BuildCreatePlatforms(BaseModel):

    name: str
    arch_list: typing.List[typing.Literal['x86_64', 'i686', 'aarch64', 'ppc64le',
                                          's390x']]


class BuildCreate(BaseModel):

    platforms: conlist(BuildCreatePlatforms, min_items=1)
    tasks: conlist(typing.Union[BuildTaskRef, BuildTaskModuleRef], min_items=1)
    linked_builds: typing.List[int] = []
    mock_options: typing.Optional[typing.Dict[str, typing.Any]]
    is_secure_boot: bool = False


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


class BuildTaskTestTask(BaseModel):

    status: int

    class Config:
        orm_mode = True


class BuildSignTask(BaseModel):

    status: int

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
    test_tasks: typing.List[BuildTaskTestTask]

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


class BuildCreateResponse(BaseModel):

    id: int
    created_at: datetime.datetime
    mock_options: typing.Optional[typing.Dict[str, typing.Any]]

    class Config:
        orm_mode = True


class Build(BaseModel):

    id: int
    created_at: datetime.datetime
    tasks: typing.List[BuildTask]
    user: BuildUser
    sign_tasks: typing.List[BuildSignTask]
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


class ModulePreviewRequest(BaseModel):

    ref: BuildTaskRef
    platform_name: str


class ModuleRef(BaseModel):

    url: str
    git_ref: str
    exist: bool
    mock_options: dict


class ModulePreview(BaseModel):

    refs: typing.List[ModuleRef]
    modules_yaml: str
    module_name: str
    module_stream: str


async def _get_module_ref(
            component_name, modified_list, platform_prefix_list,
            module, gitea_client, devel_module, platform_packages_git
        ):
    ref_prefix = platform_prefix_list['non_modified']
    if component_name in modified_list:
        ref_prefix = platform_prefix_list['modified']
    git_ref = f'{ref_prefix}-stream-{module.stream}'
    exist = True
    commit_id = ''
    try:
        response = await gitea_client.get_branch(
            f'rpms/{component_name}', git_ref
        )
        commit_id = response['commit']['id']
    except aiohttp.client_exceptions.ClientResponseError as e:
        if e.status == 404:
            exist = False
    module.set_component_ref(component_name, commit_id)
    if devel_module:
        devel_module.set_component_ref(component_name, commit_id)
    return ModuleRef(
        url=f'{platform_packages_git}{component_name}.git',
        git_ref=git_ref,
        exist=exist,
        mock_options={
            'definitions': {
                k: v for k, v in module.iter_mock_definitions()
            }
        },
        ref_type=BuildTaskRefType.GIT_BRANCH
    )


async def get_module_refs(task, platform):
    result = []
    gitea_client = GiteaClient(
        settings.gitea_host,
        logging.getLogger(__name__)
    )
    modified_list = await get_modified_refs_list(
        platform.modularity['modified_packages_url']
    )
    template = await download_modules_yaml(
        task.url,
        task.git_ref,
        BuildTaskRefType.to_text(task.ref_type)
    )
    devel_ref = task.get_dev_module()
    devel_template = None
    devel_module = None
    try:
        devel_template = await download_modules_yaml(
            devel_ref.url,
            devel_ref.git_ref,
            BuildTaskRefType.to_text(devel_ref.ref_type)
        )
        devel_module = ModuleWrapper.from_template(
            devel_template,
            name=devel_ref.git_repo_name,
            stream=devel_ref.module_stream_from_ref()
        )
    except ModulesYamlNotFoundError:
        pass
    module = ModuleWrapper.from_template(
        template,
        name=task.git_repo_name,
        stream=task.module_stream_from_ref()
    )
    platform_prefix_list = platform.modularity['git_tag_prefix']
    platform_packages_git = platform.modularity['packages_git']
    component_tasks = []
    for component_name, _ in module.iter_components():
        component_tasks.append(
            _get_module_ref(
                component_name, modified_list, platform_prefix_list,
                module, gitea_client, devel_module, platform_packages_git
            )
        )
    result = await asyncio.gather(*component_tasks)
    modules = [module.render()]
    if devel_module:
        modules.append(devel_module.render())
    return result, modules

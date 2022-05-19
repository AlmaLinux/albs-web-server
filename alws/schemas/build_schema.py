import asyncio
import typing
import logging
import datetime
import urllib.parse

import aiohttp.client_exceptions
from pydantic import BaseModel, validator, Field, conlist

from alws.config import settings
from alws.constants import BuildTaskRefType
from alws import models
from alws.utils.beholder_client import BeholderClient
from alws.utils.gitea import (
    download_modules_yaml, GiteaClient, ModulesYamlNotFoundError
)
from alws.utils.modularity import (
    ModuleWrapper,
    get_modified_refs_list,
    RpmArtifact,
)
from alws.utils.parsing import (
    clean_module_tag,
    get_clean_distr_name,
)


__all__ = ['BuildTaskRef', 'BuildCreate', 'Build', 'BuildsResponse']


class BuildTaskRef(BaseModel):

    url: str
    git_ref: typing.Optional[str]
    ref_type: typing.Optional[int]
    is_module: typing.Optional[bool] = False
    enabled: bool = True
    added_artifacts: typing.Optional[list] = []
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
        if isinstance(v, str):
            v = BuildTaskRefType.from_text(v)
        return v

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
    platform_flavors: typing.Optional[typing.List[int]] = None
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


class RpmModule(BaseModel):
    id: int
    name: str
    version: str
    stream: str
    context: str
    arch: str
    sha256: str

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
    rpm_module: typing.Optional[RpmModule]
    artifacts: typing.List[BuildTaskArtifact]
    is_secure_boot: typing.Optional[bool]
    test_tasks: typing.List[BuildTaskTestTask]
    error: typing.Optional[str]

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


class PlatformFlavour(BaseModel):

    id: int
    name: str

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
    platform_flavors: typing.List[PlatformFlavour]

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
    platform_arches: typing.List[str] = []
    flavors: typing.Optional[typing.List[int]] = None


class ModuleRef(BaseModel):

    url: str
    git_ref: str
    exist: bool
    enabled: bool = True
    added_artifacts: typing.Optional[list] = []
    mock_options: dict


class ModulePreview(BaseModel):

    refs: typing.List[ModuleRef]
    modules_yaml: str
    module_name: str
    module_stream: str


async def get_module_data_from_beholder(
    beholder_client: BeholderClient,
    endpoint: str,
    arch: str,
    devel: bool = False,
) -> dict:
    result = {}
    try:
        beholder_response = await beholder_client.get(endpoint)
    except Exception:
        logging.error('Cannot get module info')
        return result
    result['devel'] = devel
    result['arch'] = arch
    result['artifacts'] = beholder_response.get('artifacts', [])
    logging.info('Beholder result artifacts: %s', str(result['artifacts']))
    return result


def compare_module_data(
    component_name: str,
    beholder_data: typing.List[dict],
    tag_name: str,
) -> typing.List[dict]:
    pkgs_to_add = []
    for beholder_dict in beholder_data:
        beholder_artifact = None
        for artifact_dict in beholder_dict.get('artifacts', []):
            artifacr_srpm = artifact_dict.get('sourcerpm')
            if artifacr_srpm is None:
                continue
            if artifacr_srpm.get('name', '') == component_name:
                beholder_artifact = artifact_dict
                break
        if beholder_artifact is None:
            continue
        srpm = beholder_artifact['sourcerpm']
        beholder_tag_name = (f"{srpm['name']}-{srpm['version']}-"
                             f"{srpm['release']}")
        beholder_tag_name = clean_module_tag(beholder_tag_name)
        if beholder_tag_name != tag_name:
            continue
        for package in beholder_artifact['packages']:
            package['devel'] = beholder_dict.get('devel', False)
            pkgs_to_add.append(package)
    return pkgs_to_add


async def _get_module_ref(
    component_name: str,
    modified_list: list,
    platform_prefix_list: list,
    module: ModuleWrapper,
    gitea_client: GiteaClient,
    devel_module: typing.Optional[ModuleWrapper],
    platform_packages_git: str,
    beholder_data: typing.List[dict],
):
    ref_prefix = platform_prefix_list['non_modified']
    if component_name in modified_list:
        ref_prefix = platform_prefix_list['modified']
    git_ref = f'{ref_prefix}-stream-{module.stream}'
    exist = True
    commit_id = ''
    enabled = True
    pkgs_to_add = []
    added_packages = []
    clean_tag_name = ''
    try:
        response = await gitea_client.get_branch(
            f'rpms/{component_name}', git_ref
        )
        commit_id = response['commit']['id']
    except aiohttp.client_exceptions.ClientResponseError as e:
        if e.status == 404:
            exist = False
    if commit_id:
        tags = await gitea_client.list_tags(f'rpms/{component_name}')
        raw_tag_name = next((
            tag['name'] for tag in tags
            if tag['id'] == commit_id
        ), None)
        if raw_tag_name is not None:
            # we need only last part from tag to comparison
            # imports/c8-stream-rhel8/golang-1.16.7-1.module+el8.5.0+12+1aae3f
            tag_name = raw_tag_name.split('/')[-1]
            clean_tag_name = clean_module_tag(tag_name)
            pkgs_to_add = compare_module_data(
                component_name, beholder_data, clean_tag_name)
            enabled = not pkgs_to_add
    for pkg_dict in pkgs_to_add:
        if pkg_dict['devel']:
            continue
        module.add_rpm_artifact(pkg_dict)
        added_packages.append(
            RpmArtifact.from_pulp_model(pkg_dict).as_artifact())
    module.set_component_ref(component_name, commit_id)
    if devel_module:
        devel_module.set_component_ref(component_name, commit_id)
        for pkg_dict in pkgs_to_add:
            if not pkg_dict['devel']:
                continue
            devel_module.add_rpm_artifact(pkg_dict, devel=True)
            added_packages.append(
                RpmArtifact.from_pulp_model(pkg_dict).as_artifact())
    return ModuleRef(
        url=f'{platform_packages_git}{component_name}.git',
        git_ref=git_ref,
        exist=exist,
        added_artifacts=added_packages,
        enabled=enabled,
        mock_options={
            'definitions': dict(module.iter_mock_definitions()),
        },
        ref_type=BuildTaskRefType.GIT_BRANCH
    )


async def get_module_refs(
    task: BuildTaskRef,
    platform: models.Platform,
    flavors: typing.List[models.PlatformFlavour],
    platform_arches: typing.List[str] = None,
) -> typing.Tuple[typing.List[ModuleRef], typing.List[str]]:
    gitea_client = GiteaClient(
        settings.gitea_host,
        logging.getLogger(__name__)
    )

    beholder_client = BeholderClient(
        host=settings.beholder_host,
        token=settings.beholder_token,
    )
    clean_dist_name = get_clean_distr_name(platform.name)
    distr_ver = platform.distr_version
    modified_list = await get_modified_refs_list(
        platform.modularity['modified_packages_url']
    )
    template = await download_modules_yaml(
        task.url,
        task.git_ref,
        BuildTaskRefType.to_text(task.ref_type)
    )
    devel_ref = task.get_dev_module()
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
    checking_tasks = []
    if platform_arches is None:
        platform_arches = []
    for arch in platform_arches:
        request_arch = arch
        if arch == 'i686':
            request_arch = 'x86_64'
        endpoint = (
            f'/api/v1/distros/{clean_dist_name}/{distr_ver}'
            f'/module/{module.name}/{module.stream}/{request_arch}/'
        )
        checking_tasks.append(get_module_data_from_beholder(
            beholder_client, endpoint, arch))
        if devel_module is not None:
            endpoint = (
                f'/api/v1/distros/{clean_dist_name}/{distr_ver}'
                f'/module/{devel_module.name}/{devel_module.stream}/'
                f'{request_arch}/'
            )
            checking_tasks.append(get_module_data_from_beholder(
                beholder_client, endpoint, arch, devel=True))
    beholder_results = await asyncio.gather(*checking_tasks)

    platform_prefix_list = platform.modularity['git_tag_prefix']
    for flavor in flavors:
        if flavor.modularity and flavor.modularity.get('git_tag_prefix'):
            platform_prefix_list = flavor.modularity['git_tag_prefix']
    platform_packages_git = platform.modularity['packages_git']
    component_tasks = []
    for component_name, _ in module.iter_components():
        component_tasks.append(_get_module_ref(
            component_name=component_name,
            modified_list=modified_list,
            platform_prefix_list=platform_prefix_list,
            module=module,
            gitea_client=gitea_client,
            devel_module=devel_module,
            platform_packages_git=platform_packages_git,
            beholder_data=beholder_results,
        ))
    result = await asyncio.gather(*component_tasks)
    modules = [module.render()]
    if devel_module:
        modules.append(devel_module.render())
    return result, modules

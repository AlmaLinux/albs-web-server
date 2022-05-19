import logging
import asyncio
import typing
import collections
import itertools

from sqlalchemy.orm import Session, selectinload
from sqlalchemy.future import select

from alws import models
from alws.errors import DataNotFoundError, EmptyBuildError
from alws.config import settings
from alws.schemas import build_schema
from alws.constants import BuildTaskStatus, BuildTaskRefType
from alws.utils.beholder_client import BeholderClient
from alws.utils.gitea import (
    GiteaClient,
)
from alws.utils.modularity import (
    calc_dist_macro,
    IndexWrapper,
    ModuleWrapper,
    RpmArtifact,
)
from alws.utils.multilib import MultilibProcessor
from alws.utils.parsing import parse_git_ref
from alws.utils.pulp_client import PulpClient


__all__ = ['BuildPlanner']


class BuildPlanner:

    def __init__(
                self,
                db: Session,
                build: models.Build,
                platforms: typing.List[build_schema.BuildCreatePlatforms],
                platform_flavors: typing.Optional[typing.List[int]],
                is_secure_boot: bool,
            ):
        self._db = db
        self._gitea_client = GiteaClient(
            settings.gitea_host,
            logging.getLogger(__name__)
        )
        self._pulp_client = PulpClient(
            settings.pulp_host,
            settings.pulp_user,
            settings.pulp_password
        )
        self._build = build
        self._task_index = 0
        self._request_platforms = {
            platform.name: platform.arch_list for platform in platforms
        }
        self._platforms = []
        self._platform_flavors = []
        self._modules_by_target = collections.defaultdict(list)
        self._module_build_index = {}
        self._module_modified_cache = {}
        self._tasks_cache = collections.defaultdict(list)
        self._is_secure_boot = is_secure_boot
        self.load_platforms()
        if platform_flavors:
            self.load_platform_flavors(platform_flavors)

    def load_platforms(self):
        platform_names = list(self._request_platforms.keys())
        self._platforms = self._db.execute(select(models.Platform).where(
            models.Platform.name.in_(platform_names)))
        self._platforms = self._platforms.scalars().all()
        if len(self._platforms) != len(platform_names):
            found_platforms = {platform.name for platform in self._platforms}
            missing_platforms = ', '.join(
                name for name in platform_names if name not in found_platforms
            )
            raise DataNotFoundError(
                f'platforms: {missing_platforms} cannot be found in database'
            )

    def load_platform_flavors(self, flavors):
        db_flavors = self._db.execute(
            select(models.PlatformFlavour).where(
                models.PlatformFlavour.id.in_(flavors)
        ).options(
            selectinload(models.PlatformFlavour.repos)
        )).scalars().all()
        if db_flavors:
            self._platform_flavors = db_flavors

    async def create_build_repo(
                self,
                platform: models.Platform,
                arch: str,
                repo_type: str,
                is_debug: typing.Optional[bool] = False,
            ):
        debug_suffix = 'debug-' if is_debug else ''
        repo_name = (
            f'{platform.name}-{arch}-{self._build.id}-{debug_suffix}br'
        )
        repo_url, pulp_href = await self._pulp_client.create_build_rpm_repo(
            repo_name)
        modules = self._modules_by_target.get((platform.name, arch), [])
        if modules:
            await self._pulp_client.modify_repository(
                pulp_href, add=[module.pulp_href for module in modules]
            )
        repo = models.Repository(
            name=repo_name,
            url=repo_url,
            arch=arch,
            pulp_href=pulp_href,
            type=repo_type,
            debug=is_debug
        )
        self._build.repos.append(repo)

    async def init_build_repos(self):
        tasks = []
        for platform in self._platforms:
            for arch in ['src'] + self._request_platforms[platform.name]:
                tasks.append(self.create_build_repo(
                    platform,
                    arch,
                    'rpm'
                ))
                if arch == 'src':
                    continue
                tasks.append(self.create_build_repo(
                    platform,
                    arch,
                    'rpm',
                    is_debug=True
                ))
        await asyncio.gather(*tasks)

    async def add_linked_builds(self, linked_build):
        self._build.linked_builds.append(linked_build)

    @staticmethod
    async def get_multilib_artifacts(
            task: build_schema.BuildTaskModuleRef, has_devel: bool = False
    ) -> typing.List[dict]:
        beholder_client = BeholderClient(
            settings.beholder_host, token=settings.beholder_token)
        major_distr_version = task.module_platform_version.split('.')[0]
        multilib_artifacts = []

        # FIXME: Hardcoded platform for now, should send actual platform
        #  in the task ref
        multilib_packages = await MultilibProcessor.get_module_multilib_data(
            beholder_client, 'AlmaLinux', major_distr_version,
            task.module_name, task.module_stream, has_devel=has_devel)
        multilib_set = {pkg['name'] for pkg in multilib_packages}

        for ref in task.refs:
            # Skip packages that are scheduled to be built
            if ref.enabled:
                continue
            for artifact in ref.added_artifacts:
                parsed_artifact = RpmArtifact.from_str(artifact)
                if (parsed_artifact.arch == 'i686'
                        and parsed_artifact.name in multilib_set):
                    multilib_artifacts.append(parsed_artifact.as_dict())

        return multilib_artifacts

    async def prepare_module_index(
            self, task: build_schema.BuildTaskModuleRef, task_arch: str
    ) -> IndexWrapper:
        allowed_arches = (task_arch, 'src', 'noarch')
        index = IndexWrapper.from_template(task.modules_yaml)

        for module in index.iter_modules():
            for ref in task.refs:
                if ref.enabled:
                    for artifact in ref.added_artifacts:
                        module.remove_rpm_artifact(artifact)
                else:
                    for artifact in ref.added_artifacts:
                        parsed_artifact = RpmArtifact.from_str(artifact)
                        if parsed_artifact.arch in allowed_arches:
                            module.add_rpm_artifact(parsed_artifact.as_dict())
                        else:
                            module.remove_rpm_artifact(artifact)

        if task_arch == 'x86_64':
            multilib_artifacts = await self.get_multilib_artifacts(
                task, has_devel=index.has_devel_module())
            await MultilibProcessor.update_module_index(
                index, task.module_name, task.module_stream,
                multilib_artifacts
            )

        return index

    async def add_task(self, task: build_schema.BuildTaskRef):
        if isinstance(task, build_schema.BuildTaskRef) and not task.is_module:
            await self._add_single_ref(models.BuildTaskRef(
                url=task.url,
                git_ref=task.git_ref,
                ref_type=task.ref_type
            ))
            return

        if isinstance(task, build_schema.BuildTaskModuleRef):
            raw_refs = [ref for ref in task.refs if ref.enabled]
            _index = IndexWrapper.from_template(task.modules_yaml)
            module = _index.get_module(task.module_name, task.module_stream)
            devel_module = None
            try:
                devel_module = _index.get_module(
                    task.module_name + '-devel', task.module_stream
                )
            except ModuleNotFoundError:
                pass
            module_templates = [module.render()]
            if devel_module:
                module_templates.append(devel_module.render())
        else:
            raw_refs, module_templates = await build_schema.get_module_refs(
                task, self._platforms[0], self._platform_flavors
            )
        refs = [
            models.BuildTaskRef(
                url=ref.url,
                git_ref=ref.git_ref,
                ref_type=BuildTaskRefType.GIT_BRANCH
            ) for ref in raw_refs
        ]
        if not refs:
            raise EmptyBuildError
        module = None
        if self._build.mock_options:
            mock_options = self._build.mock_options.copy()
            if not mock_options.get('definitions'):
                mock_options['definitions'] = {}
        else:
            mock_options = {'definitions': {}}
        modularity_version = None
        for platform in self._platforms:
            modularity_version = platform.modularity['versions'][-1]
            for flavour in self._platform_flavors:
                if flavour.modularity and flavour.modularity.get('versions'):
                    modularity_version = flavour.modularity['versions'][-1]
            if task.module_platform_version:
                flavour_versions = [
                    flavour.modularity['versions']
                    for flavour in self._platform_flavors
                    if flavour.modularity and flavour.modularity.get('versions')
                ]
                modularity_version = next(
                    item for item in itertools.chain(
                        platform.modularity['versions'], *flavour_versions)
                    if item['name'] == task.module_platform_version
                )
            module_version = ModuleWrapper.generate_new_version(
               modularity_version['version_prefix']
            )
            if task.module_version:
                module_version = int(task.module_version)
            for arch in self._request_platforms[platform.name]:
                module_index = await self.prepare_module_index(task, arch)
                module = module_index.get_module(
                    task.module_name, task.module_stream)
                module.add_module_dependencies_from_mock_defs(
                    mock_modules=mock_options.get('module_enable', []))
                # TODO: Rework to be able to set enabled modules from UI,
                #  including ability to disable default modules from template
                mock_options['module_enable'] = [
                    f'{module.name}:{module.stream}'
                ]
                mock_options['module_enable'] += [
                    f'{dep_name}:{dep_stream}'
                    for dep_name, dep_stream in module.iter_dependencies()
                ]
                module.version = module_version
                module.context = module.generate_new_context()
                module.arch = arch
                module.set_arch_list(
                    self._request_platforms[platform.name]
                )
                module_index.add_module(module)
                if module_index.has_devel_module():
                    devel_module = module_index.get_module(
                        f'{task.module_name}', task.module_stream)
                    devel_module.version = module.version
                    devel_module.context = module.context
                    devel_module.arch = module.arch
                    devel_module.set_arch_list(
                        self._request_platforms[platform.name]
                    )
                    mock_options['module_enable'].append(
                        f'{devel_module.name}:{devel_module.stream}'
                    )
                module_pulp_href, sha256 = await self._pulp_client.create_module(
                    module_index.render(),
                    module.name,
                    module.stream,
                    module.context,
                    module.arch
                )
                db_module = models.RpmModule(
                    name=module.name,
                    version=str(module.version),
                    stream=module.stream,
                    context=module.context,
                    arch=module.arch,
                    pulp_href=module_pulp_href,
                    sha256=sha256
                )
                self._modules_by_target[(platform.name, arch)].append(
                    db_module)
        all_modules = []
        for modules in self._modules_by_target.values():
            all_modules.extend(modules)
        self._db.add_all(all_modules)
        for key, value in module.iter_mock_definitions():
            mock_options['definitions'][key] = value
        for ref in refs:
            await self._add_single_ref(
                ref,
                mock_options=mock_options,
                modularity_version=modularity_version,
            )

    async def get_ref_commit_id(self, git_name, git_branch):
        response = await self._gitea_client.get_branch(
            f'rpms/{git_name}', git_branch
        )
        return response['commit']['id']

    async def _add_single_ref(
            self,
            ref: models.BuildTaskRef,
            mock_options: typing.Optional[dict[str, typing.Any]] = None,
            modularity_version: typing.Optional[dict] = None):
        parsed_dist_macro = None
        if ref.git_ref is not None:
            parsed_dist_macro = parse_git_ref(r'(el[\d]+_[\d]+)', ref.git_ref)
        if mock_options is None:
            mock_options = {'definitions': {}}
        dist_taken_by_user = mock_options['definitions'].get('dist', False)
        for platform in self._platforms:
            arch_tasks = []
            arch_list = self._request_platforms[platform.name]
            if 'i686' in arch_list and arch_list.index('i686') != 0:
                arch_list.remove('i686')
                arch_list.insert(0, 'i686')
                self._request_platforms[platform.name] = arch_list
            for arch in self._request_platforms[platform.name]:
                modules = self._modules_by_target.get(
                    (platform.name, arch), [])
                if modules:
                    module = modules[0]
                    build_index = self._module_build_index.get(platform.name)
                    if build_index is None:
                        platform.module_build_index += 1
                        build_index = platform.module_build_index
                        self._module_build_index[platform.name] = build_index
                    platform_dist = modularity_version['dist_prefix']
                    dist_macro = calc_dist_macro(
                        module.name,
                        module.stream,
                        int(module.version),
                        module.context,
                        build_index,
                        platform_dist
                    )
                    if not dist_taken_by_user:
                        mock_options['definitions']['dist'] = dist_macro
                if not dist_taken_by_user and parsed_dist_macro:
                    mock_options['definitions']['dist'] = f'.{parsed_dist_macro}'
                build_task = models.BuildTask(
                    arch=arch,
                    platform=platform,
                    status=BuildTaskStatus.IDLE,
                    index=self._task_index,
                    ref=ref,
                    rpm_module=modules[0] if modules else None,
                    is_secure_boot=self._is_secure_boot,
                    mock_options=mock_options,
                )
                task_key = (platform.name, arch)
                self._tasks_cache[task_key].append(build_task)
                if self._task_index > 0:
                    dep = self._tasks_cache[task_key][self._task_index - 1]
                    build_task.dependencies.append(dep)
                for dep in arch_tasks:
                    build_task.dependencies.append(dep)
                arch_tasks.append(build_task)
                self._build.tasks.append(build_task)
        self._task_index += 1

    def create_build(self):
        return self._build

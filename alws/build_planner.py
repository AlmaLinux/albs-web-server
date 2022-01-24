import logging
import asyncio
import typing
import collections

import yaml
import aiohttp
from sqlalchemy.orm import Session
from sqlalchemy.future import select

from alws import models
from alws.errors import DataNotFoundError
from alws.config import settings
from alws.schemas import build_schema
from alws.constants import BuildTaskStatus, BuildTaskRefType
from alws.utils.pulp_client import PulpClient
from alws.utils.parsing import parse_git_ref
from alws.utils.modularity import ModuleWrapper, calc_dist_macro, IndexWrapper
from alws.utils.gitea import (
    download_modules_yaml, GiteaClient, ModuleNotFoundError
)


__all__ = ['BuildPlanner']


class BuildPlanner:

    def __init__(
                self,
                db: Session,
                user_id: int,
                platforms: typing.List[build_schema.BuildCreatePlatforms],
                is_secure_boot: bool,
            ):
        self._db = db
        self._gitea_client = GiteaClient(
            settings.gitea_host,
            logging.getLogger(__name__)
        )
        self._build = models.Build(user_id=user_id)
        self._task_index = 0
        self._request_platforms = {
            platform.name: platform.arch_list for platform in platforms
        }
        self._platforms = []
        self._modules_by_target = collections.defaultdict(list)
        self._module_build_index = {}
        self._module_modified_cache = {}
        self._tasks_cache = collections.defaultdict(list)
        self._is_secure_boot = is_secure_boot

    async def load_platforms(self):
        platform_names = list(self._request_platforms.keys())
        self._platforms = await self._db.execute(select(models.Platform).where(
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

    async def create_build_repo(
                self,
                pulp_client: PulpClient,
                platform: models.Platform,
                arch: str,
                repo_type: str,
                is_debug: typing.Optional[bool] = False,
                task_id: typing.Optional[int] = None
            ):
        suffix = 'br' if repo_type != 'build_log' else f'artifacts-{task_id}'
        debug_suffix = 'debug-' if is_debug else ''
        repo_name = (
            f'{platform.name}-{arch}-{self._build.id}-{debug_suffix}{suffix}'
        )
        if repo_type == 'rpm':
            repo_url, pulp_href = await pulp_client.create_build_rpm_repo(
                repo_name)
            modules = self._modules_by_target.get((platform.name, arch), [])
            if modules:
                await pulp_client.modify_repository(
                    pulp_href, add=[module.pulp_href for module in modules]
                )
        else:
            repo_url, pulp_href = await pulp_client.create_log_repo(
                repo_name)
        repo = models.Repository(
            name=repo_name,
            url=repo_url,
            arch=arch,
            pulp_href=pulp_href,
            type=repo_type,
            debug=is_debug
        )
        await self._db.run_sync(self.sync_append_build_repo, repo)

    def sync_append_build_repo(self, db: Session, repo: models.BuildRepo):
        self._build.repos.append(repo)

    def sync_get_build_tasks(self, db: Session):
        return self._build.tasks

    async def init_build_repos(self):
        pulp_client = PulpClient(
            settings.pulp_host,
            settings.pulp_user,
            settings.pulp_password
        )
        tasks = []
        for platform in self._platforms:
            for arch in ['src'] + self._request_platforms[platform.name]:
                tasks.append(self.create_build_repo(
                    pulp_client,
                    platform,
                    arch,
                    'rpm'
                ))
                if arch == 'src':
                    continue
                tasks.append(self.create_build_repo(
                    pulp_client,
                    platform,
                    arch,
                    'rpm',
                    is_debug=True
                ))
        for task in await self._db.run_sync(self.sync_get_build_tasks):
            tasks.append(self.create_build_repo(
                pulp_client,
                task.platform,
                task.arch,
                'build_log',
                task_id=task.id
            ))
        await asyncio.gather(*tasks)

    async def add_linked_builds(self, linked_build):
        self._build.linked_builds.append(linked_build)

    async def add_task(self, task: build_schema.BuildTaskRef):
        if not task.is_module:
            await self._add_single_ref(models.BuildTaskRef(
                url=task.url,
                git_ref=task.git_ref,
                ref_type=task.ref_type
            ))
            return
        refs, module_templates = await self._get_module_refs(task)
        # TODO: we should merge all of the modules before insert
        pulp_client = PulpClient(
            settings.pulp_host,
            settings.pulp_user,
            settings.pulp_password
        )
        module = None
        mock_options = {'definitions': {}}
        for platform in self._platforms:
            modularity_version = platform.modularity['versions'][-1]
            if task.module_platform_version:
                modularity_version = next(
                    item for item in platform.modularity['versions']
                    if item['name'] == task.module_platform_version
                )
            for arch in self._request_platforms[platform.name]:
                module = ModuleWrapper.from_template(module_templates[0])
                mock_options['module_enable'] = [
                    f'{module.name}:{module.stream}'
                ]
                mock_options['module_enable'] += [
                    f'{dep_name}:{dep_stream}'
                    for dep_name, dep_stream in module.iter_dependencies()
                ]
                if task.module_version is not None:
                    module.version = int(task.module_version)
                else:
                    module.version = module.generate_new_version(
                        modularity_version['version_prefix'])
                module.context = module.generate_new_context()
                module.arch = arch
                module.set_arch_list(
                    self._request_platforms[platform.name]
                )
                module_index = IndexWrapper()
                module_index.add_module(module)
                if len(module_templates) > 1:
                    devel_module = ModuleWrapper.from_template(
                        module_templates[1],
                        module.name + '-devel',
                        module.stream
                    )
                    devel_module.version = module.version
                    devel_module.context = module.context
                    devel_module.arch = module.arch
                    devel_module.set_arch_list(
                        self._request_platforms[platform.name]
                    )
                    mock_options['module_enable'].append(
                        f'{devel_module.name}:{devel_module.stream}'
                    )
                    module_index.add_module(devel_module)
                module_pulp_href, sha256 = await pulp_client.create_module(
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
                ref_platform_version=task.module_platform_version
            )

    async def _get_module_refs(self, task: build_schema.BuildTaskRef):
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
        except ModuleNotFoundError:
            pass
        module = ModuleWrapper.from_template(
            template,
            name=task.git_repo_name,
            stream=task.module_stream_from_ref()
        )
        result = []
        # TODO: we should rethink schema for multiple platforms
        #       right now there is no option to create tasks with different
        #       refs for multiple platforms
        platform = self._platforms[0]
        platform_prefix_list = platform.modularity['git_tag_prefix']
        platform_packages_git = platform.modularity['packages_git']
        for component_name, _ in module.iter_components():
            ref_prefix = platform_prefix_list['non_modified']
            if await self.is_ref_modified(platform, component_name):
                ref_prefix = platform_prefix_list['modified']
            git_ref = f'{ref_prefix}-stream-{module.stream}'
            result.append(models.BuildTaskRef(
                url=f'{platform_packages_git}{component_name}.git',
                git_ref=git_ref,
                ref_type=BuildTaskRefType.GIT_BRANCH
            ))
            ref = await self.get_ref_commit_id(component_name, git_ref)
            module.set_component_ref(component_name, ref)
            if devel_module:
                devel_module.set_component_ref(component_name, ref)
        modules = [module.render()]
        if devel_module:
            modules.append(devel_module.render())
        return result, modules

    async def get_ref_commit_id(self, git_name, git_branch):
        response = await self._gitea_client.get_branch(
            f'rpms/{git_name}', git_branch
        )
        return response['commit']['id']

    async def is_ref_modified(self, platform: models.Platform, ref: str):
        if self._module_modified_cache.get(platform.name):
            return ref in self._module_modified_cache[platform.name]
        url = platform.modularity['modified_packages_url']
        package_list = []
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as response:
                yaml_body = await response.text()
                response.raise_for_status()
                package_list = yaml.safe_load(yaml_body)['modified_packages']
        self._module_modified_cache[platform.name] = package_list
        return ref in self._module_modified_cache[platform.name]

    async def _add_single_ref(
            self,
            ref: models.BuildTaskRef,
            mock_options: typing.Optional[dict[str, typing.Any]] = None,
            ref_platform_version: typing.Optional[str] = None):
        parsed_dist_macro = parse_git_ref(r'(el[\d]+_[\d]+)', ref.git_ref)
        if mock_options is None:
            mock_options = {'definitions': {}}
        dist_taken_by_user = mock_options['definitions'].get('dist', False)
        for platform in self._platforms:
            arch_tasks = []
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
                    platform_dist = platform.modularity['versions'][-1]['dist_prefix']
                    if ref_platform_version:
                        platform_dist = next(
                            i for i in platform.modularity['versions']
                            if i['name'] == ref_platform_version
                        )['dist_prefix']
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
                    mock_options['definitions']['dist'] = parsed_dist_macro
                build_task = models.BuildTask(
                    arch=arch,
                    platform_id=platform.id,
                    status=BuildTaskStatus.IDLE,
                    index=self._task_index,
                    ref=ref,
                    rpm_module=modules[0] if modules else None,
                    is_secure_boot=self._is_secure_boot,
                    mock_options=mock_options
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

    def add_mock_options(self, mock_options: dict):
        self._build.mock_options = mock_options

    def create_build(self):
        return self._build

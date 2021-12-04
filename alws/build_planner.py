import asyncio
import typing
import collections

from sqlalchemy.orm import Session
from sqlalchemy.future import select

from alws import models
from alws.errors import DataNotFoundError
from alws.config import settings
from alws.schemas import build_schema
from alws.constants import BuildTaskStatus, BuildTaskRefType
from alws.utils.pulp_client import PulpClient
from alws.utils.modularity import ModuleWrapper, calc_dist_macro
from alws.utils.gitea import download_modules_yaml


__all__ = ['BuildPlanner']


class BuildPlanner:

    def __init__(
                self,
                db: Session,
                user_id: int,
                platforms: typing.List[build_schema.BuildCreatePlatforms]
            ):
        self._db = db
        self._build = models.Build(user_id=user_id)
        self._task_index = 0
        self._request_platforms = {
            platform.name: platform.arch_list for platform in platforms
        }
        self._platforms = []
        self._modules_by_target = {}
        self._module_build_index = {}
        self._tasks_cache = collections.defaultdict(list)

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
            module = self._modules_by_target.get((platform.name, arch))
            if module:
                await pulp_client.modify_repository(
                    pulp_href, add=[module.pulp_href]
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
            await self._add_single_ref(models.BuildTaskRef(**task.dict()))
            return
        refs, module_template = await self._get_module_refs(task)
        # TODO: we should merge all of the modules before insert
        pulp_client = PulpClient(
            settings.pulp_host,
            settings.pulp_user,
            settings.pulp_password
        )
        module = None
        mock_options = {'definitions': {}}
        for platform in self._platforms:
            for arch in self._request_platforms[platform.name]:
                module = ModuleWrapper.from_template(module_template)
                mock_options['module_enable'] = [
                    f'{module.name}:{module.stream}'
                ]
                mock_options['module_enable'] += [
                    f'{dep_name}:{dep_stream}'
                    for dep_name, dep_stream in module.iter_dependencies()
                ]
                module.version = module.generate_new_version(
                    platform.module_version_prefix)
                module.context = module.generate_new_context()
                module.arch = arch
                module.set_arch_list(platform.arch_list)
                module_pulp_href, sha256 = await pulp_client.create_module(
                    module.render())
                db_module = models.RpmModule(
                    name=module.name,
                    version=str(module.version),
                    stream=module.stream,
                    context=module.context,
                    arch=module.arch,
                    pulp_href=module_pulp_href,
                    sha256=sha256
                )
                self._modules_by_target[(platform.name, arch)] = db_module
        self._db.add_all(list(self._modules_by_target.values()))
        for key, value in module.iter_mock_definitions():
            mock_options['definitions'][key] = value
        for ref in refs:
            await self._add_single_ref(ref, mock_options=mock_options)

    async def _get_module_refs(self, task: build_schema.BuildTaskRef):
        template = await download_modules_yaml(
            task.url,
            task.git_ref,
            BuildTaskRefType.to_text(task.ref_type)
        )
        module = ModuleWrapper.from_template(
            template,
            name=task.git_repo_name,
            stream=task.module_stream_from_ref()
        )
        template = module.render()
        result = []
        for component_name, component in module.iter_components():
            result.append(models.BuildTaskRef(
                # TODO: fix this hardcode
                url=f'https://git.almalinux.org/rpms/{component_name}.git',
                # TODO: c8 should be taken from platform config
                git_ref=f'c8-stream-{module.stream}',
                ref_type=BuildTaskRefType.GIT_BRANCH
            ))
        return result, template

    async def _add_single_ref(
            self,
            ref: models.BuildTaskRef,
            mock_options: typing.Optional[dict[str, typing.Any]] = None):
        for platform in self._platforms:
            arch_tasks = []
            for arch in self._request_platforms[platform.name]:
                module = self._modules_by_target.get((platform.name, arch))
                if module:
                    build_index = self._module_build_index.get(platform.name)
                    if build_index is None:
                        platform.module_build_index += 1
                        build_index = platform.module_build_index
                        self._module_build_index[platform.name] = build_index
                    dist_macro = calc_dist_macro(
                        module.name,
                        module.stream,
                        int(module.version),
                        module.context,
                        build_index,
                        platform.data['mock_dist']
                    )
                    mock_options['definitions']['dist'] = dist_macro
                build_task = models.BuildTask(
                    arch=arch,
                    platform_id=platform.id,
                    status=BuildTaskStatus.IDLE,
                    index=self._task_index,
                    ref=ref,
                    rpm_module=module,
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

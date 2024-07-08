import asyncio
import collections
import itertools
import logging
import re
import typing

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.orm import selectinload

from alws import models
from alws.config import settings
from alws.constants import BuildTaskRefType, BuildTaskStatus
from alws.errors import DataNotFoundError, EmptyBuildError
from alws.schemas import build_schema
from alws.utils.beholder_client import BeholderClient
from alws.utils.gitea import GiteaClient
from alws.utils.modularity import (
    IndexWrapper,
    ModuleWrapper,
    RpmArtifact,
    calc_dist_macro,
)
from alws.utils.multilib import MultilibProcessor
from alws.utils.parsing import get_clean_distr_name, parse_git_ref
from alws.utils.pulp_client import PulpClient

__all__ = ['BuildPlanner']


class BuildPlanner:
    def __init__(
        self,
        db: AsyncSession,
        build: models.Build,
        is_secure_boot: bool,
        module_build_index: typing.Optional[dict],
        logger: logging.Logger,
    ):
        self._db = db
        self._gitea_client = None
        self._pulp_client = None
        self.__initialized = False
        self.logger = logger
        self._build = build
        self._task_index = 0
        self._request_platforms_arch_list = {}
        self._parallel_modes = {}
        self._platforms = []
        self._platform_flavors = []
        self._modules_by_platform_arch = collections.defaultdict(list)
        self._module_build_index = module_build_index or {}
        self._tasks_cache = collections.defaultdict(
            lambda: collections.defaultdict(list)
        )
        self._is_secure_boot = is_secure_boot

    async def init(
        self,
        platforms: typing.List[build_schema.BuildCreatePlatforms],
        platform_flavors: typing.Optional[typing.List[int]],
    ):
        if self.__initialized:
            return
        for platform in platforms:
            arch_list = platform.arch_list
            if 'i686' in arch_list and arch_list.index('i686') != 0:
                arch_list.remove('i686')
                arch_list.insert(0, 'i686')
            self._request_platforms_arch_list[platform.name] = arch_list

            self._parallel_modes[platform.name] = (
                platform.parallel_mode_enabled
            )
        await self.load_platforms()
        if platform_flavors:
            await self.load_platform_flavors(platform_flavors)
        self._gitea_client = GiteaClient(
            settings.gitea_host, logging.getLogger(__name__)
        )
        self._pulp_client = PulpClient(
            settings.pulp_host, settings.pulp_user, settings.pulp_password
        )
        self.__initialized = True

    async def load_platforms(self):
        platform_names = list(self._request_platforms_arch_list.keys())
        self._platforms = await self._db.execute(
            select(models.Platform).where(
                models.Platform.name.in_(platform_names)
            )
        )
        self._platforms = self._platforms.scalars().all()
        if len(self._platforms) != len(platform_names):
            found_platforms = {platform.name for platform in self._platforms}
            missing_platforms = ', '.join(
                name for name in platform_names if name not in found_platforms
            )
            raise DataNotFoundError(
                f'platforms: {missing_platforms} cannot be found in database'
            )

    async def load_platform_flavors(self, flavors):
        db_flavors = (
            (
                await self._db.execute(
                    select(models.PlatformFlavour)
                    .where(models.PlatformFlavour.id.in_(flavors))
                    .options(selectinload(models.PlatformFlavour.repos))
                )
            )
            .scalars()
            .all()
        )
        if db_flavors:
            self._platform_flavors = db_flavors

    def is_beta_build(self):
        if not self._platform_flavors:
            return False
        found = False
        for flavor in self._platform_flavors:
            if found := bool(
                re.search(r'(-beta)$', flavor.name, re.IGNORECASE)
            ):
                break
        return found

    async def create_build_repo(
        self,
        platform: models.Platform,
        arch: str,
        repo_type: str,
        is_debug: typing.Optional[bool] = False,
    ):
        debug_suffix = 'debug-' if is_debug else ''
        repo_name = f'{platform.name}-{arch}-{self._build.id}-{debug_suffix}br'
        repo_url, pulp_href = await self._pulp_client.create_build_rpm_repo(
            repo_name
        )
        modules = self._modules_by_platform_arch.get((platform.name, arch), [])
        if modules and not is_debug:
            await self._pulp_client.modify_repository(
                pulp_href, add=[module.pulp_href for module in modules]
            )
        repo = models.Repository(
            name=repo_name,
            url=repo_url,
            arch=arch,
            pulp_href=pulp_href,
            type=repo_type,
            debug=is_debug,
            platform=platform,
        )
        self._build.repos.append(repo)

    async def create_log_repo(
        self,
        repo_type: str,
        repo_prefix: str = 'build_logs',
    ):
        repo_name = f'build-{self._build.id}-{repo_type}'
        repo_url, repo_href = await self._pulp_client.create_log_repo(
            repo_name, distro_path_start=repo_prefix
        )
        repo = models.Repository(
            name=repo_name,
            url=repo_url,
            arch='log',
            pulp_href=repo_href,
            type=repo_type,
            debug=False,
        )
        self._build.repos.append(repo)

    async def init_build_repos(self):
        tasks = []
        # Add build log and test log repositories
        for repo_type, repo_prefix in (
            ('build_log', 'build_logs'),
            ('test_log', 'test_logs'),
        ):
            tasks.append(
                self.create_log_repo(repo_type, repo_prefix=repo_prefix)
            )

        for platform in self._platforms:
            self.logger.info(
                'Create repos for platform "%s" with id "%s"',
                platform.name,
                platform.id,
            )
            for arch in self._request_platforms_arch_list[platform.name]:
                if arch == 'src':
                    continue

                tasks.append(self.create_build_repo(platform, arch, 'rpm'))
                tasks.append(
                    self.create_build_repo(
                        platform, arch, 'rpm', is_debug=True
                    )
                )

            # Add source RPM repository
            tasks.append(self.create_build_repo(platform, 'src', 'rpm'))

        await asyncio.gather(*tasks)

    async def add_linked_builds(self, linked_build):
        self._build.linked_builds.append(linked_build)

    @staticmethod
    async def get_platform_multilib_artifacts(
        beholder_client: BeholderClient,
        platform_name: str,
        platform_version: str,
        task: build_schema.BuildTaskModuleRef,
        has_devel: bool = False,
    ) -> typing.Dict[str, typing.List[dict]]:
        multilib_artifacts = {}

        multilib_packages = await MultilibProcessor.get_module_multilib_data(
            beholder_client,
            platform_name,
            platform_version,
            task.module_name,
            task.module_stream,
            has_devel=has_devel,
        )
        multilib_set = {pkg['name'] for pkg in multilib_packages}

        for ref in task.refs:
            # Skip packages that are scheduled to be built
            if ref.enabled:
                continue
            if not ref.added_artifacts:
                continue

            project_name = ref.url.split('/')[-1].strip()
            project_name = re.sub(r'\.git$', '', project_name)
            if project_name not in multilib_artifacts:
                multilib_artifacts[project_name] = []

            for artifact in ref.added_artifacts:
                parsed_artifact = RpmArtifact.from_str(artifact)
                if (
                    parsed_artifact.arch == 'i686'
                    and parsed_artifact.name in multilib_set
                ):
                    multilib_artifacts[project_name].append(
                        parsed_artifact.as_dict()
                    )

        return multilib_artifacts

    async def get_multilib_artifacts(
        self, task: build_schema.BuildTaskModuleRef, has_devel: bool = False
    ) -> typing.Dict[str, dict]:
        if not settings.package_beholder_enabled:
            return {}

        beholder_client = BeholderClient(
            settings.beholder_host, token=settings.beholder_token
        )
        multilib_artifacts = {}

        for platform in self._platforms:
            platform_name = get_clean_distr_name(platform.name)
            multilib_artifacts[platform.name] = (
                await self.get_platform_multilib_artifacts(
                    beholder_client,
                    platform_name,
                    platform.distr_version,
                    task,
                    has_devel=has_devel,
                )
            )

        return multilib_artifacts

    @staticmethod
    def merge_beta_module_artifacts(stable: dict, beta: dict) -> dict:
        # Fast decisions before doing the merge
        if not stable and not beta:
            return {}
        elif stable and not beta:
            return stable
        elif not stable and beta:
            return beta

        merged = {}

        for module_name, projects in stable.items():
            # If no updates for modules then just copy stable data in result
            if not beta.get(module_name, {}):
                merged[module_name] = projects
                continue

            new_projects = {}
            beta_projects = beta[module_name]
            for proj_name, packages in projects.items():
                # If no updates for packages in beta data
                # then just copy data in result
                if not beta_projects.get(proj_name, []):
                    new_projects[proj_name] = packages
                    continue

                new_packages = []
                for stable_pkg in packages:
                    update_found = False
                    stable_pkg_name = stable_pkg['name']
                    stable_pkg_arch = stable_pkg['arch']
                    for beta_pkg in beta_projects[proj_name]:
                        if (
                            stable_pkg_name == beta_pkg['name']
                            and stable_pkg_arch == beta_pkg['arch']
                        ):
                            update_found = True
                            new_packages.append(beta_pkg)
                            break
                    if not update_found:
                        new_packages.append(stable_pkg)

                new_projects[proj_name] = new_packages

            merged[module_name] = new_projects

        return merged

    async def get_prebuilt_module_artifacts(
        self,
        task: build_schema.BuildTaskModuleRef,
        platform_name: str,
        platform_version: str,
        task_arch: str,
    ) -> dict:
        if not settings.package_beholder_enabled:
            return {}

        beholder = BeholderClient(
            settings.beholder_host, token=settings.beholder_token
        )
        clean_name = get_clean_distr_name(platform_name)
        arch = task_arch
        if task_arch == 'i686':
            arch = 'x86_64'
        artifacts = await beholder.get_module_artifacts(
            clean_name,
            platform_version,
            task.module_name,
            task.module_stream,
            arch,
        )

        # Include data from beta flavor for partial updates
        if self.is_beta_build():
            beta_artifacts = await beholder.get_module_artifacts(
                f'{clean_name}-beta',
                platform_version,
                task.module_name,
                task.module_stream,
                arch,
            )
            if beta_artifacts:
                artifacts = self.merge_beta_module_artifacts(
                    artifacts, beta_artifacts
                )

        reprocessed = {}
        for module_name, projects in artifacts.items():
            reprocessed[module_name] = {}
            for project_name, packages in projects.items():
                new_packages = []
                for pkg in packages:
                    if pkg['arch'] == 'x86_64' and task_arch == 'i686':
                        pkg['arch'] = 'i686'
                    new_packages.append(pkg)
                reprocessed[module_name][project_name] = new_packages
        return reprocessed

    async def prepare_module_index(
        self,
        platform: models.Platform,
        task: build_schema.BuildTaskModuleRef,
        task_arch: str,
    ) -> IndexWrapper:
        allowed_arches = (task_arch, 'src', 'noarch')
        index = IndexWrapper.from_template(task.modules_yaml)
        # Clean up all artifacts from module for re-population
        for module in index.iter_modules():
            for artifact in module.get_rpm_artifacts():
                module.remove_rpm_artifact(artifact)

        # Refill modules index with data from beholder
        built_artifacts = await self.get_prebuilt_module_artifacts(
            task, platform.name, platform.distr_version, task_arch
        )

        multilib_artifacts = {}
        if task_arch == 'x86_64':
            multilib_artifacts = await self.get_multilib_artifacts(
                task, has_devel=index.has_devel_module()
            )
            multilib_artifacts = multilib_artifacts.get(platform.name, {})
        for module in index.iter_modules():
            for ref in task.refs:
                if ref.enabled:
                    continue

                project_name = ref.url.split('/')[-1].strip()
                project_name = re.sub(r'\.git$', '', project_name)

                for artifact in ref.added_artifacts:
                    parsed_artifact = RpmArtifact.from_str(artifact)
                    if parsed_artifact.arch in allowed_arches:
                        module.add_rpm_artifact(parsed_artifact.as_dict())

                if multilib_artifacts:
                    await MultilibProcessor.update_module_index(
                        index,
                        task.module_name,
                        task.module_stream,
                        multilib_artifacts[project_name],
                        src_name=project_name,
                    )

                project_built_artifacts = built_artifacts.get(
                    module.name, {}
                ).get(project_name, [])
                if not project_built_artifacts:
                    continue
                for artifact in project_built_artifacts:
                    if artifact['arch'] in allowed_arches:
                        module.add_rpm_artifact(artifact)
        return index

    async def _add_single_project(
        self,
        ref: build_schema.BuildTaskRef,
        mock_options: typing.Optional[dict[str, typing.Any]] = None,
        modularity_version: typing.Optional[dict] = None,
    ):
        parsed_dist_macro = None
        if ref.git_ref is not None:
            parsed_dist_macro = parse_git_ref(r'(el[\d]+_[\d]+)', ref.git_ref)
        if not mock_options:
            mock_options = {'definitions': {}}
        if 'definitions' not in mock_options:
            mock_options['definitions'] = {}
        dist_taken_by_user = mock_options['definitions'].get('dist', False)
        for platform in self._platforms:
            arches = self._request_platforms_arch_list[platform.name]
            if 'src' not in arches:
                arches.insert(0, 'src')
            for arch in arches:
                modules = self._modules_by_platform_arch.get(
                    (platform.name, arch), []
                )
                if modules:
                    module = modules[0]
                    build_index = self._module_build_index.get(platform.name)
                    if not build_index:
                        raise ValueError(
                            f'Build index for {platform.name} is not defined'
                        )
                    platform_dist = modularity_version['dist_prefix']
                    dist_macro = calc_dist_macro(
                        module.name,
                        module.stream,
                        int(module.version),
                        module.context,
                        build_index,
                        platform_dist,
                    )
                    if not dist_taken_by_user:
                        mock_options['definitions']['dist'] = dist_macro
                if not dist_taken_by_user and parsed_dist_macro:
                    mock_options['definitions'][
                        'dist'
                    ] = f'.{parsed_dist_macro}'
                build_task = models.BuildTask(
                    build_id=self._build.id,
                    arch=arch,
                    platform=platform,
                    status=BuildTaskStatus.IDLE,
                    index=self._task_index,
                    ref=ref,
                    is_secure_boot=self._is_secure_boot,
                    mock_options=mock_options,
                )
                if modules:
                    build_task.rpm_modules.extend(modules)
                self._tasks_cache[platform.name][arch].append(build_task)
        self._task_index += 1

    async def _add_single_module(
        self,
        task: build_schema.BuildTaskModuleRef,
    ):
        raw_refs = [ref for ref in task.refs if ref.enabled]
        _index = IndexWrapper.from_template(task.modules_yaml)
        refs = [
            models.BuildTaskRef(
                url=ref.url,
                git_ref=ref.git_ref,
                ref_type=BuildTaskRefType.GIT_BRANCH,
                test_configuration=(
                    ref.test_configuration.model_dump()
                    if ref.test_configuration
                    else None
                ),
            )
            for ref in raw_refs
        ]
        print('Raw refs: ', raw_refs)
        print('Module refs: ', refs)
        if not refs:
            raise EmptyBuildError
        if self._build.mock_options:
            mock_options = self._build.mock_options.copy()
            if not mock_options.get('definitions'):
                mock_options['definitions'] = {}
        else:
            mock_options = {'definitions': {}}
        for platform in self._platforms:
            modularity_version = platform.modularity['versions'][-1]
            for flavour in self._platform_flavors:
                if flavour.modularity and flavour.modularity.get('versions'):
                    modularity_version = flavour.modularity['versions'][-1]
            if task.module_platform_version:
                flavour_versions = [
                    flavour.modularity['versions']
                    for flavour in self._platform_flavors
                    if flavour.modularity
                    and flavour.modularity.get('versions')
                ]
                modularity_version = next(
                    item
                    for item in itertools.chain(
                        platform.modularity['versions'], *flavour_versions
                    )
                    if item['name'] == task.module_platform_version
                )
            if task.module_version:
                module_version = int(task.module_version)
            else:
                module_version = ModuleWrapper.generate_new_version(
                    modularity_version['version_prefix']
                )
            mock_enabled_modules = mock_options.get('module_enable', [])[:]
            # Take the first task mock_options
            # as all tasks share the same mock_options
            if task.refs:
                mock_enabled_modules.extend(
                    task.refs[0].mock_options.get("module_enable", [])
                )
            for arch in self._request_platforms_arch_list[platform.name]:
                module_index = await self.prepare_module_index(
                    platform, task, arch
                )
                module = module_index.get_module(
                    task.module_name, task.module_stream
                )
                module.add_module_dependencies_from_mock_defs(
                    enabled_modules=task.enabled_modules
                )
                mock_options['module_enable'] = mock_enabled_modules
                module.version = module_version
                module.context = module.generate_new_context()
                module.arch = arch
                module.set_arch_list(
                    self._request_platforms_arch_list[platform.name]
                )
                module_index.add_module(module)
                devel_module = None
                if module_index.has_devel_module() and not module.is_devel:
                    devel_module = module_index.get_module(
                        f'{task.module_name}-devel', task.module_stream
                    )
                    devel_module.version = module.version
                    devel_module.context = module.context
                    devel_module.arch = module.arch
                    devel_module.set_arch_list(
                        self._request_platforms_arch_list[platform.name]
                    )
                    devel_module.add_module_dependency_to_devel_module(
                        module=module
                    )
                # Pulp requires usual and devel modules to be separate entities
                for module in (module, devel_module):
                    if not module:
                        continue
                    # Create fake module in pulp without final version.
                    # Final module in pulp will be created after all tasks are
                    # done.
                    # See: alws.crud.build_node.__process_build_task_artifacts
                    module_pulp_href = await self._pulp_client.create_module(
                        module.render(),
                        module.name,
                        module.stream,
                        module.context,
                        module.arch,
                        module.description,
                        artifacts=module.get_rpm_artifacts(),
                        dependencies=list(module.get_runtime_deps().values()),
                        packages=[],
                        profiles=module.get_profiles(),
                    )
                    # Create module in db.
                    # It has the final version and pulp_href is pointing
                    # to the fake module in pulp created above.
                    db_module = models.RpmModule(
                        name=module.name,
                        version=str(module.version),
                        stream=module.stream,
                        context=module.context,
                        arch=module.arch,
                        pulp_href=module_pulp_href,
                    )
                    self._modules_by_platform_arch[
                        (platform.name, arch)
                    ].append(db_module)
                all_modules = []
                for modules in self._modules_by_platform_arch.values():
                    all_modules.extend(modules)
                self._db.add_all(all_modules)
                for key, value in module.iter_mock_definitions():
                    mock_options['definitions'][key] = value
            for ref in refs:
                await self._add_single_project(
                    ref,
                    mock_options=mock_options,
                    modularity_version=modularity_version,
                )

    async def add_git_project(
        self,
        ref: typing.Union[
            build_schema.BuildTaskRef,
            build_schema.BuildTaskModuleRef,
        ],
    ):
        if isinstance(ref, build_schema.BuildTaskRef):
            db_ref = models.BuildTaskRef(
                url=ref.url,
                git_ref=ref.git_ref,
                ref_type=ref.ref_type,
                test_configuration=(
                    ref.test_configuration.model_dump()
                    if ref.test_configuration
                    else None
                ),
            )
            await self._add_single_project(db_ref)
        else:
            await self._add_single_module(ref)

    async def build_dependency_map(self):
        # TODO: Make sources build as first "arch" in all process
        # Make dependencies between the tasks as following:
        #   - If platform has i686 architecture then process it first;
        #   - If i686 is absent then pick any architecture as first;
        #   - Other architectures should depend on first architecture
        #     for the corresponding project only;
        #   - All architectures should have dependencies
        #     between their own tasks to ensure correct build order.
        all_tasks = []
        for platform_task_cache in self._tasks_cache.values():
            first_arch = 'src'
            first_arch_tasks = platform_task_cache.get(first_arch)
            if not first_arch_tasks:
                first_arch = next(iter(platform_task_cache))
                first_arch_tasks = platform_task_cache.get(first_arch)
            for index in range(1, len(first_arch_tasks)):
                previous_task_index = index - 1
                current_task = first_arch_tasks[index]
                previous_task = first_arch_tasks[previous_task_index]
                current_task.dependencies.append(previous_task)
            all_tasks.extend(first_arch_tasks)
            # If it's the only arch, do not need to go additional cycle
            if len(platform_task_cache.keys()) == 1:
                continue
            for arch, tasks in platform_task_cache.items():
                if arch == first_arch:
                    continue
                # Add dependency between first task of first architecture
                # and first task of each following architecture
                tasks[0].dependencies.append(first_arch_tasks[0])
                # Add dependencies for all other tasks
                for index in range(1, len(tasks)):
                    previous_tasks = tasks[:index]
                    first_arch_task = first_arch_tasks[index]
                    current_task = tasks[index]
                    current_task.dependencies.extend(
                        [first_arch_task, *previous_tasks]
                    )
                all_tasks.extend(tasks)
        self._db.add_all(all_tasks)

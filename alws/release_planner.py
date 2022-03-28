import asyncio
import re
import copy
import typing
from collections import defaultdict

from sqlalchemy.future import select
from sqlalchemy.orm import Session, selectinload

from alws import models
from alws.config import settings
from alws.constants import ReleaseStatus, RepoType, PackageNevra
from alws.crud import sign_task
from alws.errors import (
    DataNotFoundError,
    EmptyReleasePlan,
    MissingRepository,
    ReleaseLogicError,
    SignError,
)
from alws.schemas import release_schema
from alws.utils.beholder_client import BeholderClient
from alws.utils.debuginfo import is_debuginfo_rpm
from alws.utils.modularity import IndexWrapper
from alws.utils.parsing import get_clean_distr_name
from alws.utils.pulp_client import PulpClient


class ReleasePlanner:
    def __init__(self, db: Session):
        self._db = db
        self.pkgs_mapping = None
        self.repo_data_by_href = None
        self.pkgs_nevra = None
        self.debug_pkgs_nevra = None
        self.existing_packages = None
        self.latest_repo_versions = None
        self.base_platform = None
        self._beholder_client = BeholderClient(settings.beholder_host)
        self._pulp_client = PulpClient(
            settings.pulp_host,
            settings.pulp_user,
            settings.pulp_password
        )

    async def get_pulp_packages(
        self,
        build_ids: typing.List[int],
        build_tasks: typing.List[int] = None,
    ) -> typing.Tuple[typing.List[dict], typing.List[str], typing.List[dict]]:
        src_rpm_names = []
        packages_fields = ['name', 'epoch', 'version', 'release', 'arch']
        pulp_packages = []

        builds_q = select(models.Build).where(
            models.Build.id.in_(build_ids)).options(
            selectinload(
                models.Build.source_rpms).selectinload(
                models.SourceRpm.artifact),
            selectinload(
                models.Build.binary_rpms).selectinload(
                models.BinaryRpm.artifact),
            selectinload(models.Build.tasks).selectinload(
                models.BuildTask.rpm_module
            ),
            selectinload(models.Build.repos)
        )
        build_result = await self._db.execute(builds_q)
        modules_to_release = {}
        for build in build_result.scalars().all():
            for rpm_data in (build.source_rpms, build.binary_rpms):
                for rpm in rpm_data:
                    # Failsafe to not process logs
                    if rpm.artifact.type != 'rpm':
                        continue
                    artifact_task_id = rpm.artifact.build_task_id
                    if build_tasks and artifact_task_id not in build_tasks:
                        continue
                    artifact_name = rpm.artifact.name
                    if '.src.' in artifact_name:
                        src_rpm_names.append(artifact_name)
                    pkg_info = await self._pulp_client.get_rpm_package(
                        rpm.artifact.href, include_fields=packages_fields)
                    pkg_info['artifact_href'] = rpm.artifact.href
                    pkg_info['full_name'] = artifact_name
                    build_task = next(
                        task for task in build.tasks
                        if task.id == artifact_task_id
                    )
                    pkg_info['task_arch'] = build_task.arch
                    pkg_info['force'] = False
                    pulp_packages.append(pkg_info)
            for task in build.tasks:
                if task.rpm_module and task.id in build_tasks:
                    key = (
                        task.rpm_module.name,
                        task.rpm_module.stream,
                        task.rpm_module.version,
                        task.rpm_module.arch
                    )
                    if key in modules_to_release:
                        continue
                    module_repo = next(
                        build_repo for build_repo in task.build.repos
                        if build_repo.arch == task.arch
                        and not build_repo.debug
                        and build_repo.type == 'rpm'
                    )
                    template = await self._pulp_client.get_repo_modules_yaml(
                        module_repo.url)
                    module_index = IndexWrapper.from_template(template)
                    for module in module_index.iter_modules():
                        modules_to_release[key] = {
                            'build_id': build.id,
                            'name': module.name,
                            'stream': module.stream,
                            'version': module.version,
                            'context': module.context,
                            'arch': module.arch,
                            'template': module.render()
                        }
        return pulp_packages, src_rpm_names, list(modules_to_release.values())

    async def check_package_presence_in_repo(
        self,
        pkgs_nevra: dict,
        repo_ver_href: str,
        repo_id: int,
        arch: str,
    ):
        params = {
            'name__in': ','.join(pkgs_nevra['name']),
            'epoch__in': ','.join(pkgs_nevra['epoch']),
            'version__in': ','.join(pkgs_nevra['version']),
            'release__in': ','.join(pkgs_nevra['release']),
            'arch': arch,
            'repository_version': repo_ver_href,
            'fields': 'pulp_href,name,epoch,version,release,arch',
        }
        pulp_packages_by_params = await self._pulp_client.get_rpm_packages(
            params)
        if pulp_packages_by_params:
            for pkg in pulp_packages_by_params:
                full_name = self.pkgs_mapping.get(PackageNevra(
                    pkg['name'], pkg['epoch'], pkg['version'],
                    pkg['release'], pkg['arch'],
                ))
                if full_name is None:
                    continue
                self.existing_packages[full_name].append((pkg['pulp_href'],
                                                          repo_id))

    async def prepare_data_for_executing_async_tasks(self,
                                                     package: dict) -> None:
        # create collections for checking packages in repos
        if self.pkgs_nevra is None:
            self.pkgs_nevra = {arch: defaultdict(set)
                               for arch in ('noarch', 'src')}
            self.pkgs_nevra.update({
                arch: defaultdict(set)
                for arch in self.base_platform.arch_list
            })
            self.debug_pkgs_nevra = copy.deepcopy(self.pkgs_nevra)
            self.existing_packages = defaultdict(list)
            self.pkgs_mapping = {}
            self.repo_data_by_href = {}
            # self.repos_by_arches = defaultdict(list)
            tasks = []
            for repo in self.base_platform.repos:
                # self.repos_by_arches[repo.arch].append(repo.id)
                self.repo_data_by_href[repo.pulp_href] = (repo.id, repo.arch)
                tasks.append(self._pulp_client.get_repo_latest_version(
                    repo.pulp_href, for_releases=True))
            self.latest_repo_versions = await asyncio.gather(*tasks)

        nevra = PackageNevra(
            package['name'],
            package['epoch'],
            package['version'],
            package['release'],
            package['arch']
        )
        self.pkgs_mapping[nevra] = package['full_name']
        pkg_dict = self.pkgs_nevra
        if is_debuginfo_rpm(nevra.name):
            pkg_dict = self.debug_pkgs_nevra
        pkg_dict[nevra.arch]['name'].add(nevra.name)
        pkg_dict[nevra.arch]['epoch'].add(nevra.epoch)
        pkg_dict[nevra.arch]['version'].add(nevra.version)
        pkg_dict[nevra.arch]['release'].add(nevra.release)

    async def prepare_and_execute_async_tasks(self, packages) -> dict:
        tasks = []
        packages_from_repos = {}
        for is_debug in (True, False):
            pkg_dict = self.debug_pkgs_nevra if is_debug else self.pkgs_nevra
            for pkg_arch in pkg_dict.keys():
                if not pkg_dict[pkg_arch]:
                    continue
                for repo_ver_href, repo_is_debug in self.latest_repo_versions:
                    if repo_is_debug is not is_debug:
                        continue
                    repo_href = re.sub(r'versions\/\d+\/$', '', repo_ver_href)
                    repo_id, repo_arch = self.repo_data_by_href[repo_href]
                    # we should check all repos only for noarch packages,
                    # for other packages check repos by package arch
                    if pkg_arch != 'noarch' and repo_arch != pkg_arch:
                        continue
                    tasks.append(self.check_package_presence_in_repo(
                        pkg_dict[pkg_arch], repo_ver_href, repo_id, pkg_arch))
        await asyncio.gather(*tasks)
        # if packages was founded in pulp prod repos with same NEVRA,
        # we should take them package hrefs by priority arches from platform
        # instead of package hrefs from build repo
        for pkg_info in packages:
            pkg = pkg_info['package']
            full_name = pkg['full_name']
            existing_packages_data = next((
                data for data in self.existing_packages.get(full_name, ())
                if None not in data
            ), None)
            if existing_packages_data is None:
                continue
            pkg_href, repo_id = existing_packages_data
            pkg['artifact_href'] = pkg_href
            packages_from_repos[full_name] = repo_id
        return packages_from_repos

    async def get_pulp_based_response(
        self,
        pulp_packages: list,
        rpm_modules: list,
        repos_mapping: dict,
        prod_repos: list,
        clean_base_dist_name_lower: str,
        base_platform_distr_version: str,
    ) -> dict:
        packages = []
        added_packages = set()
        for pkg in pulp_packages:
            full_name = pkg['full_name']
            if full_name in added_packages:
                continue
            await self.prepare_data_for_executing_async_tasks(pkg)
            release_repo = repos_mapping[RepoType(
                '-'.join((
                    clean_base_dist_name_lower,
                    base_platform_distr_version,
                    'devel'
                )),
                pkg['task_arch'],
                False
            )]
            packages.append({
                'package': pkg,
                'repositories': [release_repo]
            })
            added_packages.add(full_name)
        packages_from_repos = await self.prepare_and_execute_async_tasks(
            packages)

        return {
            'packages': packages,
            'repositories': prod_repos,
            'packages_from_repos': packages_from_repos,
            'modules': rpm_modules,
        }

    async def get_release_plan(
        self,
        build_ids: typing.List[int],
        base_platform: models.Platform,
        reference_platform: models.Platform,
        build_tasks: typing.List[int] = None,
    ) -> dict:
        packages = []
        rpm_modules = []
        beholder_cache = {}
        repos_mapping = {}
        strong_arches = defaultdict(list)
        added_packages = set()
        prod_repos = []
        self.base_platform = base_platform
        repo_name_regex = re.compile(r'\w+-\d-(?P<name>\w+(-\w+)?)')

        pulp_packages, src_rpm_names, pulp_rpm_modules = (
            await self.get_pulp_packages(build_ids, build_tasks=build_tasks))

        clean_base_dist_name = get_clean_distr_name(base_platform.name)
        if clean_base_dist_name is None:
            raise ValueError(f'Base distribution name is malformed: '
                             f'{base_platform.name}')
        clean_base_dist_name_lower = clean_base_dist_name.lower()

        clean_ref_dist_name = get_clean_distr_name(reference_platform.name)
        if clean_ref_dist_name is None:
            raise ValueError(f'Reference distribution name is malformed: '
                             f'{reference_platform.name}')

        for repo in base_platform.repos:
            repo_dict = {
                'id': repo.id,
                'name': repo.name,
                'arch': repo.arch,
                'debug': repo.debug,
                'url': repo.url,
            }
            repo_key = RepoType(repo.name, repo.arch, repo.debug)
            repos_mapping[repo_key] = repo_dict
            prod_repos.append(repo_dict)

        for weak_arch in base_platform.weak_arch_list:
            strong_arches[weak_arch['depends_on']].append(weak_arch['name'])

        if not settings.package_beholder_enabled:
            return await self.get_pulp_based_response(
                pulp_packages=pulp_packages,
                rpm_modules=rpm_modules,
                repos_mapping=repos_mapping,
                prod_repos=prod_repos,
                clean_base_dist_name_lower=clean_base_dist_name_lower,
                base_platform_distr_version=base_platform.distr_version,
            )

        for module in pulp_rpm_modules:
            module_arch_list = [module['arch']]
            for strong_arch, weak_arches in strong_arches.items():
                if module['arch'] in weak_arches:
                    module_arch_list.append(strong_arch)
            endpoints = [
                f'/api/v1/distros/{dist_name}/'
                f'{reference_platform.distr_version}/module/{module["name"]}/'
                f'{module["stream"]}/{module_arch}/'
                for dist_name in [clean_ref_dist_name, base_platform.name]
                for module_arch in module_arch_list
            ]
            module_response = None
            for endpoint in endpoints:
                try:
                    module_response = await self._beholder_client.get(endpoint)
                except Exception:
                    pass
            module_info = {
                'module': module,
                'repositories': []
            }
            rpm_modules.append(module_info)
            if not module_response:
                continue
            for _packages in module_response['artifacts']:
                for pkg in _packages['packages']:
                    key = (pkg['name'], pkg['version'], pkg['arch'])
                    beholder_cache[key] = pkg
                    for weak_arch in strong_arches[pkg['arch']]:
                        second_key = (pkg['name'], pkg['version'], weak_arch)
                        replaced_pkg = copy.deepcopy(pkg)
                        for repo in replaced_pkg['repositories']:
                            if repo['arch'] == pkg['arch']:
                                repo['arch'] = weak_arch
                        beholder_cache[second_key] = replaced_pkg
            module_repo = module_response['repository']
            repo_name = repo_name_regex.search(
                module_repo['name']).groupdict()['name']
            release_repo_name = '-'.join((
                clean_base_dist_name_lower,
                base_platform.distr_version,
                repo_name
            ))
            module_info['repositories'].append({
                'name': release_repo_name,
                'arch': module_repo['arch'],
                'debug': False
            })

        endpoint = (f'/api/v1/distros/{clean_ref_dist_name}/'
                    f'{reference_platform.distr_version}/projects/')
        beholder_response = await self._beholder_client.post(endpoint,
                                                             src_rpm_names)
        for pkg_list in beholder_response.get('packages', {}):
            for pkg in pkg_list['packages']:
                key = (pkg['name'], pkg['version'], pkg['arch'])
                beholder_cache[key] = pkg
                for weak_arch in strong_arches[pkg['arch']]:
                    second_key = (pkg['name'], pkg['version'], weak_arch)
                    replaced_pkg = copy.deepcopy(pkg)
                    for repo in replaced_pkg['repositories']:
                        if repo['arch'] == pkg['arch']:
                            repo['arch'] = weak_arch
                    beholder_cache[second_key] = replaced_pkg
        if not beholder_cache:
            return await self.get_pulp_based_response(
                pulp_packages=pulp_packages,
                rpm_modules=rpm_modules,
                repos_mapping=repos_mapping,
                prod_repos=prod_repos,
                clean_base_dist_name_lower=clean_base_dist_name_lower,
                base_platform_distr_version=base_platform.distr_version,
            )
        for package in pulp_packages:
            pkg_name = package['name']
            pkg_version = package['version']
            pkg_arch = package['arch']
            full_name = package['full_name']
            if full_name in added_packages:
                continue
            await self.prepare_data_for_executing_async_tasks(package)
            key = (pkg_name, pkg_version, pkg_arch)
            predicted_package = beholder_cache.get(key, [])
            pkg_info = {'package': package, 'repositories': []}
            release_repositories = set()
            repositories = []
            if not predicted_package:
                continue
            repositories = predicted_package['repositories']
            for repo in repositories:
                ref_repo_name = repo['name']
                repo_name = (
                    repo_name_regex.search(ref_repo_name).groupdict()['name']
                )
                release_repo_name = '-'.join((
                    clean_base_dist_name_lower,
                    base_platform.distr_version,
                    repo_name
                ))
                debug = ref_repo_name.endswith('debuginfo')
                if repo['arch'] == 'src':
                    debug = False
                release_repo = RepoType(release_repo_name, repo['arch'], debug)
                release_repositories.add(release_repo)
            pkg_info['repositories'] = [
                repos_mapping.get(item) for item in release_repositories
            ]
            added_packages.add(full_name)
            packages.append(pkg_info)

        for package in pulp_packages:
            if package['full_name'] in added_packages:
                continue
            added_packages.add(package['full_name'])
            release_repo = repos_mapping[RepoType(
                '-'.join((
                    clean_base_dist_name_lower,
                    base_platform.distr_version,
                    'devel'
                )),
                package['task_arch'],
                False
            )]
            pkg_info = {
                'package': package,
                'repositories': [release_repo]
            }
            packages.append(pkg_info)

        packages_from_repos = await self.prepare_and_execute_async_tasks(
            packages)
        return {
            'packages': packages,
            'packages_from_repos': packages_from_repos,
            'modules': rpm_modules,
            'repositories': prod_repos,
        }

    async def execute_release_plan(self, release: models.Release,
                                   release_plan: dict) -> None:
        packages_to_repo_layout = {}
        if not release_plan.get('packages') or (
                not release_plan.get('repositories')):
            raise EmptyReleasePlan('Cannot execute plan with empty packages '
                                    'or repositories: {packages}, {repositories}'
                                    .format_map(release_plan))
        for build_id in release.build_ids:
            try:
                verified = await sign_task.verify_signed_build(
                    self._db, build_id, release.platform.id)
            except (DataNotFoundError, ValueError, SignError) as e:
                msg = f'The build {build_id} was not verified, because\n{e}'
                raise SignError(msg)
            if not verified:
                msg = f'Cannot execute plan with wrong singing of {build_id}'
                raise SignError(msg)

        # check packages presence in prod repos
        self.base_platform = release.platform
        for pkg_dict in release_plan['packages']:
            await self.prepare_data_for_executing_async_tasks(
                pkg_dict['package'])
        pkgs_from_repos = await self.prepare_and_execute_async_tasks(
            release_plan['packages'])
        release_plan['packages_from_repos'] = pkgs_from_repos

        for package_dict in release_plan['packages']:
            package = package_dict['package']
            pkg_full_name = package['full_name']
            force_flag = package.get('force', False)
            existing_repo_ids = [
                repo_id
                for _, repo_id in self.existing_packages.get(pkg_full_name, [])
            ]
            for repository in package_dict['repositories']:
                repo_id = repository['id']
                repo_name = repository['name']
                repo_arch = repository['arch']
                if repo_id in existing_repo_ids and not force_flag:
                    full_repo_name = (
                        f"{repo_name}-"
                        f"{'debug-' if repository['debug'] else ''}"
                        f"{repo_arch}"
                    )
                    raise ReleaseLogicError(
                        f'Cannot release {pkg_full_name} in {full_repo_name}, '
                        f'force release is disabled'
                    )
                if repo_name not in packages_to_repo_layout:
                    packages_to_repo_layout[repo_name] = {}
                if repo_arch not in packages_to_repo_layout[repo_name]:
                    packages_to_repo_layout[repo_name][repo_arch] = []
                packages_to_repo_layout[repo_name][repo_arch].append(
                    package['artifact_href'])

        for module in release_plan.get('modules', []):
            for repository in module['repositories']:
                repo_name = repository['name']
                repo_arch = repository['arch']
                if repo_name not in packages_to_repo_layout:
                    packages_to_repo_layout[repo_name] = {}
                if repo_arch not in packages_to_repo_layout[repo_name]:
                    packages_to_repo_layout[repo_name][repo_arch] = []
                module_info = module['module']
                module_pulp_href, _ = await self._pulp_client.create_module(
                    module_info['template'],
                    module_info['name'],
                    module_info['stream'],
                    module_info['context'],
                    module_info['arch']
                )
                packages_to_repo_layout[repo_name][repo_arch].append(
                    module_pulp_href)

        modify_tasks = []
        publication_tasks = []
        for repository_name, arches in packages_to_repo_layout.items():
            for arch, packages in arches.items():
                repo_q = select(models.Repository).where(
                    models.Repository.name == repository_name,
                    models.Repository.arch == arch
                )
                repo_result = await self._db.execute(repo_q)
                repo = repo_result.scalars().first()
                if not repo:
                    raise MissingRepository(
                        f'Repository with name {repository_name} is missing '
                        f'or doesn\'t have pulp_href field')
                modify_tasks.append(self._pulp_client.modify_repository(
                    repo.pulp_href, add=packages))
                # after modify repo we need to publish repo content
                publication_tasks.append(
                    self._pulp_client.create_rpm_publication(repo.pulp_href))
        await asyncio.gather(*modify_tasks)
        await asyncio.gather(*publication_tasks)

    async def create_new_release(
                self, user_id: int, payload: release_schema.ReleaseCreate
            ) -> models.Release:
        async with self._db.begin():
            user_q = select(models.User).where(models.User.id == user_id)
            user_result = await self._db.execute(user_q)
            platform_result = await self._db.execute(
                select(models.Platform).where(
                    models.Platform.id.in_(
                        (payload.platform_id, payload.reference_platform_id)
                    )
                ).options(selectinload(models.Platform.repos.and_(
                    models.Repository.production.is_(True)
                )))
            )
            platforms = platform_result.scalars().all()
            base_platform = next(item for item in platforms
                                 if item.id == payload.platform_id)
            reference_platform = next(
                item for item in platforms
                if item.id == payload.reference_platform_id
            )

            user = user_result.scalars().first()
            new_release = models.Release()
            new_release.build_ids = payload.builds
            if getattr(payload, 'build_tasks', None):
                new_release.build_task_ids = payload.build_tasks
            new_release.platform = base_platform
            new_release.reference_platform_id = payload.reference_platform_id
            new_release.plan = await self.get_release_plan(
                build_ids=payload.builds,
                base_platform=base_platform,
                reference_platform=reference_platform,
                build_tasks=payload.build_tasks
            )
            new_release.created_by = user
            self._db.add(new_release)
            await self._db.commit()

        await self._db.refresh(new_release)
        release_res = await self._db.execute(select(models.Release).where(
            models.Release.id == new_release.id).options(
            selectinload(models.Release.created_by),
            selectinload(models.Release.platform)
        ))
        return release_res.scalars().first()

    async def update_release(
            self, release_id: int,
            payload: release_schema.ReleaseUpdate
    ) -> models.Release:
        async with self._db.begin():
            query = select(models.Release).where(
                models.Release.id == release_id
            ).options(
                selectinload(models.Release.created_by),
                selectinload(models.Release.platform).selectinload(
                    models.Platform.repos.and_(
                        models.Repository.production.is_(True)
                    ),
                ),
            ).with_for_update()
            release_result = await self._db.execute(query)
            release = release_result.scalars().first()
            if not release:
                raise DataNotFoundError(
                    f'Release with ID {release_id} not found')
            if payload.plan:
                # check packages presence in prod repos
                self.base_platform = release.platform
                for pkg_dict in payload.plan['packages']:
                    await self.prepare_data_for_executing_async_tasks(
                        pkg_dict['package'])
                pkgs_from_repos = await self.prepare_and_execute_async_tasks(
                    payload.plan['packages'])
                payload.plan['packages_from_repos'] = pkgs_from_repos
                release.plan = payload.plan
            build_tasks = getattr(payload, 'build_tasks', None)
            if (payload.builds and payload.builds != release.build_ids) or (
                    build_tasks and build_tasks != release.build_task_ids):
                release.build_ids = payload.builds
                if build_tasks:
                    release.build_task_ids = payload.build_tasks
                reference_platform = await self._db.execute(
                    select(models.Platform).where(
                        models.Platform.id == release.reference_platform_id
                    )
                )
                reference_platform = reference_platform.scalars().first()
                release.plan = await self.get_release_plan(
                    build_ids=payload.builds,
                    base_platform=release.platform,
                    reference_platform=reference_platform,
                    build_tasks=payload.build_tasks,
                )
            self._db.add(release)
            await self._db.commit()
        await self._db.refresh(release)
        return release


    async def commit_release(self, release_id: int) -> (models.Release, str):
        async with self._db.begin():
            query = select(models.Release).where(
                models.Release.id == release_id
            ).options(
                selectinload(models.Release.created_by),
                selectinload(models.Release.platform).selectinload(
                    models.Platform.repos.and_(
                        models.Repository.production.is_(True)
                    ),
                ),
            ).with_for_update()
            release_result = await self._db.execute(query)
            release = release_result.scalars().first()
            if not release:
                raise DataNotFoundError(
                    f'Release with ID {release_id} not found')
            builds_q = select(models.Build).where(
                models.Build.id.in_(release.build_ids))
            builds_result = await self._db.execute(builds_q)
            for build in builds_result.scalars().all():
                build.release = release
                self._db.add(build)
            release.status = ReleaseStatus.IN_PROGRESS
            # for updating plan during executing, we should use deepcopy
            release_plan = copy.deepcopy(release.plan)
            try:
                await self.execute_release_plan(release, release_plan)
            except (EmptyReleasePlan, MissingRepository,
                    SignError, ReleaseLogicError) as e:
                message = f'Cannot commit release: {str(e)}'
                release.status = ReleaseStatus.FAILED
            else:
                message = 'Successfully committed release'
                release.status = ReleaseStatus.COMPLETED
            release_plan['last_log'] = message
            release.plan = release_plan
            self._db.add(release)
            await self._db.commit()
        await self._db.refresh(release)
        return release, message

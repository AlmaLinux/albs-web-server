import asyncio
import re
import copy
import logging
import traceback
import typing
from abc import ABCMeta, abstractmethod
from collections import defaultdict

from cas_wrapper import CasWrapper
from sqlalchemy import update, or_
from sqlalchemy.future import select
from sqlalchemy.orm import Session, selectinload

from alws import models
from alws.config import settings
from alws.constants import ReleaseStatus, RepoType, PackageNevra
from alws.crud import (
    products as product_crud,
    sign_task,
    user as user_crud,
)
from alws.errors import (
    DataNotFoundError,
    EmptyReleasePlan,
    MissingRepository,
    PermissionDenied,
    ReleaseLogicError,
    SignError,
)
from alws.perms import actions
from alws.perms.authorization import can_perform
from alws.schemas import release_schema
from alws.constants import ErrataPackageStatus
from alws.utils.beholder_client import BeholderClient
from alws.utils.debuginfo import is_debuginfo_rpm, clean_debug_name
from alws.utils.modularity import IndexWrapper, ModuleWrapper
from alws.utils.parsing import get_clean_distr_name, slice_list
from alws.utils.pulp_client import PulpClient


__all__ = [
    'CommunityReleasePlanner',
    'AlmaLinuxReleasePlanner',
    'get_releaser_class',
]


class BaseReleasePlanner(metaclass=ABCMeta):
    def __init__(self, db: Session):
        self._db = db
        self.pulp_client = PulpClient(
            settings.pulp_host,
            settings.pulp_user,
            settings.pulp_password,
        )
        self.codenotary_enabled = settings.codenotary_enabled
        if self.codenotary_enabled:
            self._cas_wrapper = CasWrapper(
                settings.cas_api_key,
                settings.cas_signer_id,
            )

    @property
    def db(self):
        return self._db

    @abstractmethod
    def get_production_pulp_repositories_names(
            self, product: models.Product = None,
            platform: models.Platform = None,
    ):
        raise NotImplementedError()

    @abstractmethod
    async def get_release_plan(
            self,
            base_platform: models.Platform,
            build_ids: typing.List[int],
            build_tasks: typing.List[int] = None,
            product: models.Product = None,
    ) -> dict:
        raise NotImplementedError()

    @abstractmethod
    async def update_release_plan(
            self, plan: dict,
            release: models.Release,
    ) -> dict:
        raise NotImplementedError()

    @abstractmethod
    async def execute_release_plan(
            self, release: models.Release
    ) -> typing.List[str]:
        raise NotImplementedError()

    @staticmethod
    def is_beta_build(build: models.Build) -> bool:
        return False

    @staticmethod
    def is_debug_repository(repo_name: str) -> bool:
        return bool(re.search(r'debug(info|source|)', repo_name))

    async def authenticate_package(self, package_checksum: str):
        is_authenticated = False
        if self.codenotary_enabled:
            is_authenticated = self._cas_wrapper.authenticate_artifact(
                package_checksum, use_hash=True)
        return package_checksum, is_authenticated

    async def get_production_pulp_repositories(
            self, product: models.Product = None,
            platform: models.Platform = None,
    ):
        repo_names = self.get_production_pulp_repositories_names(
            product=product, platform=platform)
        params = {
            'name__in': ','.join(repo_names),
            'fields': ','.join(('pulp_href', 'name',
                                'latest_version_href')),
            'limit': 1000,
        }
        pulp_repos = await self.pulp_client.get_rpm_repositories(params)
        return {
            repo.pop('pulp_href'): repo
            for repo in pulp_repos
        }

    async def get_pulp_packages(
        self,
        build_ids: typing.List[int],
        build_tasks: typing.List[int] = None,
    ) -> typing.Tuple[typing.List[dict], typing.List[str], typing.List[dict]]:

        src_rpm_names = []
        packages_fields = [
            'name',
            'epoch',
            'version',
            'release',
            'arch',
            'pulp_href',
            'sha256',
        ]
        pulp_packages = []

        builds_q = select(models.Build).where(
            models.Build.id.in_(build_ids)
        ).options(
            selectinload(models.Build.platform_flavors),
            selectinload(models.Build.source_rpms)
            .selectinload(models.SourceRpm.artifact),
            selectinload(models.Build.binary_rpms)
            .selectinload(models.BinaryRpm.artifact),
            selectinload(models.Build.binary_rpms)
            .selectinload(models.BinaryRpm.source_rpm)
            .selectinload(models.SourceRpm.artifact),
            selectinload(models.Build.tasks)
            .selectinload(models.BuildTask.rpm_module),
            selectinload(models.Build.repos),
        )
        build_result = await self.db.execute(builds_q)
        modules_to_release = defaultdict(list)
        for build in build_result.scalars().all():
            build_rpms = build.source_rpms + build.binary_rpms
            pulp_artifacts = await asyncio.gather(*(
                self.pulp_client.get_rpm_package(
                    rpm.artifact.href, include_fields=packages_fields)
                for rpm in build_rpms
                if build_tasks and rpm.artifact.build_task_id in build_tasks
            ))
            pulp_artifacts = {
                artifact_dict.pop('pulp_href'): artifact_dict
                for artifact_dict in pulp_artifacts
            }
            for rpm in build_rpms:
                artifact_task_id = rpm.artifact.build_task_id
                if build_tasks and artifact_task_id not in build_tasks:
                    continue
                artifact_name = rpm.artifact.name
                pkg_info = copy.deepcopy(pulp_artifacts[rpm.artifact.href])
                pkg_info['is_beta'] = self.is_beta_build(build)
                pkg_info['build_id'] = build.id
                pkg_info['artifact_href'] = rpm.artifact.href
                pkg_info['cas_hash'] = rpm.artifact.cas_hash
                pkg_info['href_from_repo'] = None
                pkg_info['full_name'] = artifact_name
                build_task = next(
                    task for task in build.tasks
                    if task.id == artifact_task_id
                )
                pkg_info['task_arch'] = build_task.arch
                pkg_info['force'] = False
                pkg_info['force_not_notarized'] = False
                source_rpm = getattr(rpm, 'source_rpm', None)
                if source_rpm:
                    source_name = source_rpm.artifact.name
                if '.src.rpm' in artifact_name:
                    src_rpm_names.append(artifact_name)
                    source_name = artifact_name
                pkg_info['source'] = source_name
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
                    template = await self.pulp_client.get_repo_modules_yaml(
                        module_repo.url)
                    module_index = IndexWrapper.from_template(template)
                    for module in module_index.iter_modules():
                        # in some cases we have also devel module in template,
                        # we should add all modules from template
                        modules_to_release[key].append({
                            'build_id': build.id,
                            'name': module.name,
                            'stream': module.stream,
                            'version': module.version,
                            'context': module.context,
                            'arch': module.arch,
                            'template': module.render()
                        })
        pulp_rpm_modules = [
            module_dict
            for module_list in modules_to_release.values()
            for module_dict in module_list
        ]
        return pulp_packages, src_rpm_names, pulp_rpm_modules

    async def __get_final_release(self, release_id: int) -> models.Release:
        release_res = await self.db.execute(select(models.Release).where(
            models.Release.id == release_id).options(
            selectinload(models.Release.owner),
            selectinload(models.Release.platform),
            selectinload(models.Release.product),
        ))
        return release_res.scalars().first()

    async def __get_release_for_update(self, release_id) -> models.Release:
        query = select(models.Release).where(
            models.Release.id == release_id
        ).options(
            selectinload(models.Release.owner),
            selectinload(models.Release.owner).selectinload(
                models.User.oauth_accounts),
            selectinload(models.Release.owner).selectinload(
                models.User.roles).selectinload(models.UserRole.actions),
            selectinload(models.Release.owner).selectinload(
                models.User.oauth_accounts),
            selectinload(models.Release.team).selectinload(
                models.Team.roles).selectinload(models.UserRole.actions),
            selectinload(models.Release.platform).selectinload(
                models.Platform.reference_platforms),
            selectinload(models.Release.platform).selectinload(
                models.Platform.repos.and_(
                    models.Repository.production.is_(True)
                ),
            ),
            selectinload(models.Release.product).selectinload(
                models.Product.repositories),
        ).with_for_update()
        release_result = await self.db.execute(query)
        release = release_result.scalars().first()
        return release

    async def create_new_release(
        self,
        user_id: int,
        payload: release_schema.ReleaseCreate,
    ) -> models.Release:
        user = await user_crud.get_user(self.db, user_id=user_id)
        logging.info('User %d is creating a release', user_id)

        platform = await self.db.execute(
            select(models.Platform).where(
                models.Platform.id == payload.platform_id,
            ).options(
                selectinload(models.Platform.reference_platforms),
                selectinload(models.Platform.repos.and_(
                    models.Repository.production.is_(True))),
                selectinload(models.Platform.roles).selectinload(
                    models.UserRole.actions)
            ),
        )
        platform = platform.scalars().first()
        product = await product_crud.get_products(
            self.db, product_id=payload.product_id)

        builds = (await self.db.execute(
            select(models.Build).where(
                models.Build.id.in_(payload.builds)).options(
                selectinload(models.Build.team).selectinload(
                    models.Team.roles).selectinload(
                    models.UserRole.actions)
            )
        )).scalars().all()

        for build in builds:
            if not can_perform(build, user, actions.ReleaseBuild.name):
                raise PermissionDenied(f'User does not have permissions '
                                       f'to release build {build.id}')

        if not can_perform(product, user, actions.ReleaseToProduct.name):
            raise PermissionDenied('User does not have permissions '
                                   'to release to this product')

        new_release = models.Release()
        new_release.build_ids = payload.builds
        if getattr(payload, 'build_tasks', None):
            new_release.build_task_ids = payload.build_tasks
        new_release.platform = platform
        new_release.plan = await self.get_release_plan(
            base_platform=platform,
            build_ids=payload.builds,
            build_tasks=payload.build_tasks,
            product=product
        )
        new_release.owner = user
        new_release.team_id = product.team_id
        new_release.product_id = product.id
        self.db.add(new_release)
        await self.db.commit()
        await self.db.refresh(new_release)

        logging.info('New release %d successfully created', new_release.id)
        return await self.__get_final_release(new_release.id)

    async def update_release(
        self, release_id: int,
        payload: release_schema.ReleaseUpdate,
        user_id: int
    ) -> models.Release:
        logging.info('Updating release %d', release_id)
        user = await user_crud.get_user(self.db, user_id=user_id)

        release = await self.__get_release_for_update(release_id)
        if not release:
            raise DataNotFoundError(
                f'Release with ID {release_id} not found')

        if not can_perform(release, user, actions.ReleaseToProduct.name):
            raise PermissionDenied('User does not have permissions '
                                   'to update release')

        build_tasks = getattr(payload, 'build_tasks', None)
        if (payload.builds and payload.builds != release.build_ids) or (
                build_tasks and build_tasks != release.build_task_ids):
            release.build_ids = payload.builds
            if build_tasks:
                release.build_task_ids = payload.build_tasks
            release.plan = await self.get_release_plan(
                base_platform=release.platform,
                build_ids=payload.builds,
                build_tasks=payload.build_tasks,
                product=release.product
            )
        elif payload.plan:
            # check packages presence in prod repos
            new_plan = await self.update_release_plan(
                payload.plan, release)
            release.plan = new_plan
        self.db.add(release)
        await self.db.commit()
        await self.db.refresh(release)
        logging.info('Successfully updated release %d', release_id)
        return await self.__get_final_release(release.id)

    async def commit_release(
        self,
        release_id: int,
        user_id: int,
    ) -> typing.Tuple[models.Release, str]:
        logging.info('Commiting release %d', release_id)

        user = await user_crud.get_user(self.db, user_id=user_id)
        release = await self.__get_release_for_update(release_id)
        if not release:
            raise DataNotFoundError(
                f'Release with ID {release_id} not found')

        if not can_perform(release, user, actions.ReleaseToProduct.name):
            raise PermissionDenied('User does not have permissions '
                                   'to commit the release')

        builds_released = False
        try:
            release_messages = await self.execute_release_plan(release)
        except (EmptyReleasePlan, MissingRepository,
                SignError, ReleaseLogicError) as e:
            message = f'Cannot commit release: {str(e)}'
            release.status = ReleaseStatus.FAILED
        except Exception:
            message = f"Cannot commit release:\n{traceback.format_exc()}"
            release.status = ReleaseStatus.FAILED
        else:
            message = 'Successfully committed release'
            if release_messages:
                message += '\nWARNING:\n'
                message += '\n'.join(release_messages)
            release.status = ReleaseStatus.COMPLETED
            builds_released = True

        await self._db.execute(
            update(models.Build)
            .where(models.Build.id.in_(release.build_ids))
            .values(release_id=release.id, released=builds_released)
        )
        # for updating release plan, we should use deepcopy
        release_plan = copy.deepcopy(release.plan)
        release_plan['last_log'] = message
        release.plan = release_plan
        self.db.add(release)
        await self.db.commit()
        await self.db.refresh(release)
        logging.info('Successfully committed release %d', release_id)
        release = await self.__get_final_release(release_id)
        return release, message


class CommunityReleasePlanner(BaseReleasePlanner):

    @staticmethod
    def get_repo_pretty_name(repo_name: str) -> str:
        arch_regex = re.compile(r'(i686|x86_64|aarch64|ppc64le|s390x)')
        debug_part = '-debug'

        pretty_name = re.search(
            r'(\w+-\d+)-(\w+)(-debug)?', repo_name).group()

        if not bool(arch_regex.search(pretty_name)):
            arch_res = arch_regex.search(repo_name)
            if bool(arch_res):
                pretty_name += f'-{arch_res.group()}'

        if debug_part in repo_name and debug_part not in pretty_name:
            pretty_name += debug_part

        return pretty_name

    @staticmethod
    def get_production_repositories_mapping(
            product: models.Product,
            include_pulp_href: bool = False
    ) -> dict:
        result = {}

        for repo in product.repositories:
            main_info = {
                'id': repo.id,
                'name': CommunityReleasePlanner.get_repo_pretty_name(repo.name),
                'url': repo.url,
                'arch': repo.arch,
                'debug': repo.debug
            }
            if include_pulp_href:
                main_info['pulp_href'] = repo.pulp_href
            result[(repo.arch, repo.debug)] = main_info

        return result

    async def get_release_plan(
            self,
            base_platform: models.Platform,
            build_ids: typing.List[int],
            build_tasks: typing.List[int] = None,
            product: models.Product = None) -> dict:

        release_plan = {'modules': {}}

        db_repos_mapping = self.get_production_repositories_mapping(product)

        (
            pulp_packages,
            src_rpm_names,
            pulp_rpm_modules
        ) = await self.get_pulp_packages(build_ids, build_tasks=build_tasks)

        release_plan['repositories'] = list(db_repos_mapping.values())

        plan_packages = []
        for pkg in pulp_packages:
            is_debug = is_debuginfo_rpm(pkg['full_name'])
            arch = pkg['arch']
            if arch == 'noarch':
                repositories = [db_repos_mapping[(a, is_debug)]
                                for a in base_platform.arch_list]
            else:
                repositories = [db_repos_mapping[(arch, is_debug)]]
            repo_arch_location = [arch]
            if arch == 'noarch':
                repo_arch_location = base_platform.arch_list
            plan_packages.append({
                'package': pkg,
                'repositories': repositories,
                'repo_arch_location': repo_arch_location
            })
        release_plan['packages'] = plan_packages

        if pulp_rpm_modules:
            plan_modules = []
            for module in pulp_rpm_modules:
                # Modules go only in non-debug repos
                repository = db_repos_mapping[(module['arch'], False)]
                plan_modules.append({
                    'module': module,
                    'repositories': [repository]
                })
            release_plan['modules'] = plan_modules

        return release_plan

    async def update_release_plan(
            self, plan: dict, release: models.Release) -> dict:
        # We do not need to take additional actions for release update
        # right now
        return plan

    async def execute_release_plan(
            self, release: models.Release
    ) -> typing.List[str]:
        if not release.plan.get('packages') or (
                not release.plan.get('repositories')):
            raise EmptyReleasePlan(
                'Cannot execute plan with empty packages or repositories: '
                '{packages}, {repositories}'.format_map(release.plan)
            )

        repository_modification_mapping = defaultdict(list)
        db_repos_mapping = self.get_production_repositories_mapping(
            release.product, include_pulp_href=True)

        for pkg in release.plan['packages']:
            package = pkg['package']
            for repository in pkg['repositories']:
                repo_key = (repository['arch'], repository['debug'])
                db_repo = db_repos_mapping[repo_key]
                repository_modification_mapping[db_repo['pulp_href']].append(
                    package['artifact_href'])

        # TODO: Add support for modules releases
        #       and checking existent packages in repos

        await asyncio.gather(*(
            self.pulp_client.modify_repository(href, add=packages)
            for href, packages in repository_modification_mapping.items()
        ))
        await asyncio.gather(*(
            self.pulp_client.create_rpm_publication(href)
            for href in repository_modification_mapping.keys()
        ))

        return []

    def get_production_pulp_repositories_names(
            self, product: models.Product = None,
            platform: models.Platform = None,
    ):
        pl_name_lower = platform.name.lower()
        return [r.name for r in product.repositories
                if pl_name_lower in r.name]


class AlmaLinuxReleasePlanner(BaseReleasePlanner):
    def __init__(self, db: Session):
        super().__init__(db)
        self.packages_presence_info = defaultdict(list)
        self.pkgs_mapping = {}
        self.repo_data_by_href = {}
        self.pkgs_nevra = None
        self.debug_pkgs_nevra = None
        self.latest_repo_versions = None
        self.base_platform = None
        self.clean_base_dist_name_lower = None
        self.repo_name_regex = re.compile(
            r'\w+-\d-(beta-|)(?P<name>\w+(-\w+)?)')
        self.max_list_len = 100  # max elements in list for pulp request
        self._beholder_client = BeholderClient(settings.beholder_host)
        self.codenotary_enabled = settings.codenotary_enabled
        if self.codenotary_enabled:
            self._cas_wrapper = CasWrapper(
                settings.cas_api_key,
                settings.cas_signer_id,
            )

    @staticmethod
    def is_beta_build(build: models.Build):
        if not hasattr(build, 'platform_flavors'):
            return False
        if not build.platform_flavors:
            return False
        # Search for beta flavor
        found = False
        for flavor in build.platform_flavors:
            if bool(re.search(r'(-beta)$', flavor.name, re.IGNORECASE)):
                found = True
                break
        return found

    async def check_package_presence_in_repo(
        self,
        pkg_names: list,
        pkgs_nevra: dict,
        repo_ver_href: str,
        repo_id: int,
        arch: str,
        repo_arch: str,
    ):
        params = {
            'name__in': ','.join(pkg_names),
            'epoch__in': ','.join(pkgs_nevra['epoch']),
            'version__in': ','.join(pkgs_nevra['version']),
            'release__in': ','.join(pkgs_nevra['release']),
            'arch': arch,
            'repository_version': repo_ver_href,
            'fields': 'pulp_href,name,epoch,version,release,arch',
        }
        pulp_packages_by_params = await self.pulp_client.get_rpm_packages(
            **params)
        if pulp_packages_by_params:
            for pkg in pulp_packages_by_params:
                full_name = self.pkgs_mapping.get(PackageNevra(
                    pkg['name'], pkg['epoch'], pkg['version'],
                    pkg['release'], pkg['arch'],
                ))
                if full_name is None:
                    continue
                data = (pkg['pulp_href'], repo_id, repo_arch)
                self.packages_presence_info[full_name].append(data)

    def get_production_pulp_repositories_names(
            self, product: models.Product = None,
            platform: models.Platform = None,
    ):
        return [f'{repo.name}-{repo.arch}'
                for repo in self.base_platform.repos]

    async def prepare_data_for_executing_async_tasks(
        self,
        package: dict,
        is_debug: bool,
    ) -> None:
        # create collections for checking packages in repos
        if self.pkgs_nevra is None:
            self.pkgs_nevra = {arch: defaultdict(set)
                               for arch in ('noarch', 'src')}
            self.pkgs_nevra.update({
                arch: defaultdict(set)
                for arch in self.base_platform.arch_list
            })
            self.debug_pkgs_nevra = copy.deepcopy(self.pkgs_nevra)
            self.packages_presence_info = defaultdict(list)
            if self.clean_base_dist_name_lower is None:
                self.clean_base_dist_name_lower = get_clean_distr_name(
                    self.base_platform.name).lower()

            pulp_repos = await self.get_production_pulp_repositories()
            self.latest_repo_versions = []
            for repo in self.base_platform.repos:
                pulp_repo_info = pulp_repos[repo.pulp_href]
                self.repo_data_by_href[repo.pulp_href] = (repo.id, repo.arch)
                repo_is_debug = self.is_debug_repository(pulp_repo_info['name'])
                self.latest_repo_versions.append((
                    pulp_repo_info['latest_version_href'], repo_is_debug))

        nevra = PackageNevra(
            package['name'],
            package['epoch'],
            package['version'],
            package['release'],
            package['arch']
        )
        self.pkgs_mapping[nevra] = package['full_name']
        pkg_dict = self.debug_pkgs_nevra if is_debug else self.pkgs_nevra
        pkg_dict[nevra.arch]['name'].add(nevra.name)
        pkg_dict[nevra.arch]['epoch'].add(nevra.epoch)
        pkg_dict[nevra.arch]['version'].add(nevra.version)
        pkg_dict[nevra.arch]['release'].add(nevra.release)

    async def prepare_and_execute_async_tasks(
        self,
        packages: typing.List[dict],
    ) -> typing.Tuple[dict, dict]:
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
                    pkgs_nevra = pkg_dict[pkg_arch]
                    # in cases when we releasing large build,
                    # we failed with too large pulp request line
                    sliced_pkg_names = slice_list(list(pkgs_nevra['name']),
                                                  self.max_list_len)
                    for pkg_names in sliced_pkg_names:
                        tasks.append(self.check_package_presence_in_repo(
                            pkg_names,
                            pkgs_nevra,
                            repo_ver_href,
                            repo_id,
                            pkg_arch,
                            repo_arch,
                        ))
        await asyncio.gather(*tasks)
        pkgs_in_repos = defaultdict(list)
        for pkg_info in packages:
            pkg = pkg_info['package']
            full_name = pkg['full_name']
            pkg_presence_by_repo_arch = defaultdict(list)
            presence_info = self.packages_presence_info.get(full_name)
            data = None
            if presence_info is None:
                continue
            # if packages was founded in pulp prod repos with same NEVRA,
            # we should take their hrefs by priority arches from platform
            for href, repo_id, repo_arch in presence_info:
                pkgs_in_repos[full_name].append(repo_id)
                pkg_presence_by_repo_arch[repo_arch].append((href, repo_id))
            for repo_arch in pkg_presence_by_repo_arch:
                if repo_arch == 'i686':
                    continue
                if repo_arch in self.base_platform.copy_priority_arches:
                    data = pkg_presence_by_repo_arch[repo_arch][0]
                    break
                data = pkg_presence_by_repo_arch[repo_arch][0]
            if data is None:
                continue
            repo_pkg_href, repo_id = data
            pkg['href_from_repo'] = repo_pkg_href
            packages_from_repos[full_name] = repo_id
        return packages_from_repos, pkgs_in_repos

    def get_devel_repo_key(
        self,
        arch: str,
        is_debug: bool,
        task_arch: typing.Optional[str] = None,
        is_module: bool = False,
    ):
        repo_name = '-'.join((
            self.clean_base_dist_name_lower,
            self.base_platform.distr_version,
            'devel-debuginfo' if is_debug else 'devel',
        ))
        if is_module:
            repo_arch = arch
        else:
            repo_arch = arch if arch == 'src' else task_arch
        return RepoType(repo_name, repo_arch, is_debug)

    def get_devel_repo(
        self,
        arch: str,
        is_debug: bool,
        repos_mapping: dict,
        task_arch: typing.Optional[str] = None,
        is_module: bool = False,
    ) -> typing.Optional[dict]:

        devel_repo_key = self.get_devel_repo_key(
            arch,
            is_debug,
            task_arch=task_arch,
            is_module=is_module,
        )
        devel_repo = repos_mapping.get(devel_repo_key)
        if devel_repo is None:
            logging.debug(
                "Cannot find devel repo for %s by key: %s",
                "module" if is_module else "package",
                devel_repo_key,
            )
        return devel_repo

    async def get_pulp_based_response(
        self,
        pulp_packages: list,
        rpm_modules: list,
        repos_mapping: dict,
        prod_repos: list,
    ) -> dict:
        packages = []
        added_packages = set()
        for package in pulp_packages:
            full_name = package['full_name']
            package_arch = package['arch']
            package.pop('is_beta')
            is_debug = is_debuginfo_rpm(package['name'])
            if full_name in added_packages:
                continue
            await self.prepare_data_for_executing_async_tasks(
                package, is_debug)
            devel_repo = self.get_devel_repo(
                arch=package_arch,
                is_debug=is_debug,
                repos_mapping=repos_mapping,
                task_arch=package['task_arch'],
            )
            if devel_repo is None:
                logging.debug(
                    "Skipping package=%s, repositories is missing",
                    full_name,
                )
                continue
            repo_arch_location = [package_arch]
            if package_arch == 'noarch':
                repo_arch_location = self.base_platform.arch_list
            packages.append({
                'package': package,
                'repositories': [devel_repo],
                'repo_arch_location': repo_arch_location,
            })
            added_packages.add(full_name)
        (
            pkgs_from_repos,
            pkgs_in_repos,
        ) = await self.prepare_and_execute_async_tasks(packages)

        return {
            'packages': packages,
            'repositories': prod_repos,
            'packages_from_repos': pkgs_from_repos,
            'packages_in_repos': pkgs_in_repos,
            'modules': rpm_modules,
        }

    @staticmethod
    def update_beholder_cache(
        beholder_cache: dict,
        packages: typing.List[dict],
        strong_arches: dict,
        is_beta: bool,
        is_devel: bool,
    ):

        def generate_key(pkg_arch: str = None) -> typing.Tuple:
            arch = pkg_arch if pkg_arch else pkg['arch']
            return (pkg['name'], pkg['version'], arch, is_beta, is_devel)

        for pkg in packages:
            key = generate_key()
            beholder_cache[key] = pkg
            for weak_arch in strong_arches[pkg['arch']]:
                second_key = generate_key(pkg_arch=weak_arch)
                # if we've already found repos for i686 arch
                # we don't need to override them,
                # because there can be multilib info
                beholder_repos = (
                    beholder_cache.get(second_key, {})
                    .get('repositories', [])
                )
                if beholder_repos and weak_arch == 'i686':
                    continue
                replaced_pkg = copy.deepcopy(pkg)
                for repo in replaced_pkg['repositories']:
                    if repo['arch'] == pkg['arch']:
                        repo['arch'] = weak_arch
                beholder_cache[second_key] = replaced_pkg

    def find_release_repos(
        self,
        pkg_name: str,
        pkg_version: str,
        pkg_arch: str,
        is_beta: bool,
        is_devel: bool,
        is_debug: bool,
        beholder_cache: dict,
    ) -> typing.Set[RepoType]:
        release_repositories = set()
        beholder_key = (pkg_name, pkg_version, pkg_arch, is_beta, is_devel)
        logging.debug('At find_release_repos - beholder_key: %s',
                      str(beholder_key))
        predicted_package = beholder_cache.get(beholder_key, {})
        # if we doesn't found info from stable/beta,
        # we can try to find info by opposite stable/beta flag
        if not predicted_package:
            beholder_key = (pkg_name, pkg_version, pkg_arch,
                            not is_beta, is_devel)
            logging.debug('Not predicted_package, beholder_key: %s',
                          str(beholder_key))
            predicted_package = beholder_cache.get(beholder_key, {})
        # if we doesn't found info by current version,
        # then we should try find info by other versions
        if not predicted_package:
            beholder_keys = [
                (name, version, arch, beta, devel)
                for name, version, arch, beta, devel in beholder_cache
                if all((
                    pkg_name == name,
                    pkg_arch == arch,
                    is_devel == devel,
                ))
            ]
            logging.debug('Still not predicted_package, beholder_keys: %s',
                          str(beholder_keys))
            predicted_package = next((
                beholder_cache[beholder_key]
                for beholder_key in beholder_keys
            ), {})
        for repo in predicted_package.get('repositories', []):
            ref_repo_name = repo['name']
            repo_name = (
                self.repo_name_regex.search(ref_repo_name).groupdict()['name']
            )
            # in cases if we try to find debug repos by non debug name
            if is_debug and not repo_name.endswith('debuginfo'):
                repo_name += '-debuginfo'
            release_repo_name = '-'.join((
                self.clean_base_dist_name_lower,
                self.base_platform.distr_version,
                repo_name
            ))
            release_repo = RepoType(release_repo_name, repo['arch'], is_debug)
            release_repositories.add(release_repo)
        return release_repositories

    async def get_release_plan(
        self,
        build_ids: typing.List[int],
        base_platform: models.Platform,
        build_tasks: typing.List[int] = None,
        product: models.Product = None,
    ) -> dict:
        packages = []
        rpm_modules = []
        beholder_cache = {}
        repos_mapping = {}
        strong_arches = defaultdict(list)
        added_packages = set()
        prod_repos = []
        self.base_platform = base_platform

        pulp_packages, src_rpm_names, pulp_rpm_modules = (
            await self.get_pulp_packages(build_ids, build_tasks=build_tasks))

        clean_base_dist_name = get_clean_distr_name(base_platform.name)
        if clean_base_dist_name is None:
            raise ValueError(f'Base distribution name is malformed: '
                             f'{base_platform.name}')
        self.clean_base_dist_name_lower = clean_base_dist_name.lower()

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
            rpm_modules = [
                {'module': module, 'repositories': []}
                for module in rpm_modules
            ]
            return await self.get_pulp_based_response(
                pulp_packages=pulp_packages,
                rpm_modules=rpm_modules,
                repos_mapping=repos_mapping,
                prod_repos=prod_repos,
            )

        for module in pulp_rpm_modules:
            module_name = module['name']
            module_stream = module['stream']
            module_arch_list = [module['arch']]
            module_nvsca = (
                f"{module_name}:{module['version']}:{module_stream}:"
                f"{module['context']}:{module['arch']}"
            )
            for strong_arch, weak_arches in strong_arches.items():
                if module['arch'] in weak_arches:
                    module_arch_list.append(strong_arch)
            module_responses = await self._beholder_client.retrieve_responses(
                base_platform,
                module_name,
                module_stream,
                module_arch_list,
                is_module=True,
            )
            module_info = {
                'module': module,
                'repositories': []
            }
            if not module_responses:
                devel_repo = self.get_devel_repo(
                    arch=module['arch'],
                    is_debug=False,
                    repos_mapping=repos_mapping,
                    is_module=True,
                )
                if devel_repo is None:
                    logging.debug(
                        "Skipping module=%s, repositories is missing",
                        module_nvsca
                    )
                    continue
                module_info['repositories'].append(devel_repo)
            rpm_modules.append(module_info)
            for module_response in module_responses:
                distr = module_response['distribution']
                is_beta = distr['version'].endswith('-beta')
                is_devel = module_response['name'].endswith('-devel')
                for _packages in module_response['artifacts']:
                    self.update_beholder_cache(
                        beholder_cache,
                        _packages['packages'],
                        strong_arches,
                        is_beta,
                        is_devel,
                    )
                module_repo = module_response['repository']
                repo_name = self.repo_name_regex.search(
                    module_repo['name']).groupdict()['name']
                release_repo_name = '-'.join((
                    self.clean_base_dist_name_lower,
                    base_platform.distr_version,
                    repo_name
                ))
                repo_key = RepoType(release_repo_name, module['arch'], False)
                prod_repo = repos_mapping.get(repo_key)
                if prod_repo is None:
                    logging.debug(
                        "Skipping module=%s, cannot find prod repo by key: %s",
                        module_nvsca,
                        repo_key,
                    )
                    continue
                module_repo_dict = {
                    'name': repo_key.name,
                    'arch': repo_key.arch,
                    'debug': repo_key.debug,
                    'url': prod_repo['url'],
                }
                if module_repo_dict in module_info['repositories']:
                    continue
                module_info['repositories'].append(module_repo_dict)

        beholder_responses = await self._beholder_client.retrieve_responses(
            base_platform,
            data={'source_rpms': src_rpm_names, 'match': 'closest'},
        )
        for beholder_response in beholder_responses:
            distr = beholder_response['distribution']
            is_beta = distr['version'].endswith('-beta')
            is_devel = False
            for pkg_list in beholder_response.get('packages', {}):
                self.update_beholder_cache(
                    beholder_cache,
                    pkg_list['packages'],
                    strong_arches,
                    is_beta,
                    is_devel,
                )
        if not beholder_cache:
            return await self.get_pulp_based_response(
                pulp_packages=pulp_packages,
                rpm_modules=rpm_modules,
                repos_mapping=repos_mapping,
                prod_repos=prod_repos,
            )
        logging.debug('beholder_cache: %s', str(beholder_cache))
        for package in pulp_packages:
            pkg_name = package['name']
            pkg_version = package['version']
            pkg_arch = package['arch']
            full_name = package['full_name']
            is_beta = package.pop('is_beta')
            is_debug = is_debuginfo_rpm(pkg_name)
            if full_name in added_packages:
                continue
            await self.prepare_data_for_executing_async_tasks(
                package, is_debug)
            release_repository_keys = set()
            release_repositories = defaultdict(set)
            for is_devel in (False, True):
                repositories = self.find_release_repos(
                    pkg_name=pkg_name,
                    pkg_version=pkg_version,
                    pkg_arch=pkg_arch,
                    is_debug=is_debug,
                    is_beta=is_beta,
                    is_devel=is_devel,
                    beholder_cache=beholder_cache,
                )
                # if we doesn't found repos for debug package, we can try to
                # find repos by same package name but without debug suffix
                if not repositories and is_debug:
                    repositories = self.find_release_repos(
                        pkg_name=clean_debug_name(pkg_name),
                        pkg_version=pkg_version,
                        pkg_arch=pkg_arch,
                        is_debug=is_debug,
                        is_beta=is_beta,
                        is_devel=is_devel,
                        beholder_cache=beholder_cache,
                    )
                release_repository_keys.update(repositories)
            pulp_repo_arch_location = [pkg_arch]
            if pkg_arch == 'noarch':
                pulp_repo_arch_location = self.base_platform.arch_list
            pkg_info = {
                'package': package,
                'repositories': [],
                'repo_arch_location': pulp_repo_arch_location,
            }
            if not release_repository_keys:
                devel_repo = self.get_devel_repo(
                    arch=pkg_arch,
                    is_debug=is_debug,
                    repos_mapping=repos_mapping,
                    task_arch=package['task_arch'],
                )
                if devel_repo is None:
                    logging.debug(
                        "Skipping package=%s, repositories is missing",
                        full_name,
                    )
                    continue
                pkg_info['repositories'].append(devel_repo)
                packages.append(pkg_info)
                added_packages.add(full_name)
                continue
            for release_repo_key in release_repository_keys:
                release_repo = repos_mapping.get(release_repo_key)
                # in some cases we get repos that we can't match
                if release_repo is None:
                    logging.debug(
                        "Skipping package=%s, "
                        "cannot find prod repo by key: %s",
                        full_name,
                        release_repo_key,
                    )
                    continue
                repo_arch_location = [release_repo['arch']]
                # we should add i686 arch for correct multilib showing in UI
                if pkg_arch == 'i686' and 'x86_64' in repo_arch_location:
                    repo_arch_location.append('i686')
                if pkg_arch == 'noarch':
                    repo_arch_location = pulp_repo_arch_location
                release_repositories[release_repo_key].update(
                    repo_arch_location
                )
            # for every repository we should add pkg_info
            # for correct package location in UI
            for repo_key, repo_arches in release_repositories.items():
                repo = repos_mapping[repo_key]
                copy_pkg_info = copy.deepcopy(pkg_info)
                copy_pkg_info.update({
                    # TODO: need to send only one repo instead of list
                    'repositories': [repo],
                    'repo_arch_location': list(repo_arches),
                })
                packages.append(copy_pkg_info)
            added_packages.add(full_name)

        (
            pkgs_from_repos,
            pkgs_in_repos,
        ) = await self.prepare_and_execute_async_tasks(packages)
        return {
            'packages': packages,
            'packages_from_repos': pkgs_from_repos,
            'packages_in_repos': pkgs_in_repos,
            'modules': rpm_modules,
            'repositories': prod_repos,
        }

    async def execute_release_plan(
            self, release: models.Release
    ) -> typing.List[str]:
        additional_messages = []
        authenticate_tasks = []
        packages_mapping = {}
        packages_to_repo_layout = {}
        if not release.plan.get('packages') or (
                not release.plan.get('repositories')):
            raise EmptyReleasePlan(
                'Cannot execute plan with empty packages or repositories: '
                '{packages}, {repositories}'.format_map(release.plan)
            )
        for build_id in release.build_ids:
            try:
                verified = await sign_task.verify_signed_build(
                    self.db, build_id, release.platform.id)
            except (DataNotFoundError, ValueError, SignError) as e:
                msg = f'The build {build_id} was not verified, because\n{e}'
                raise SignError(msg)
            if not verified:
                msg = f'Cannot execute plan with wrong singing of {build_id}'
                raise SignError(msg)

        # check packages presence in prod repos
        self.base_platform = release.platform
        for pkg_dict in release.plan['packages']:
            package = pkg_dict['package']
            is_debug = is_debuginfo_rpm(package['name'])
            await self.prepare_data_for_executing_async_tasks(
                package, is_debug)
            if self.codenotary_enabled:
                authenticate_tasks.append(
                    self.authenticate_package(package['sha256'])
                )
        (
            pkgs_from_repos,
            pkgs_in_repos,
        ) = await self.prepare_and_execute_async_tasks(
            release.plan['packages'],
        )
        release.plan['packages_from_repos'] = pkgs_from_repos
        release.plan['packages_in_repos'] = pkgs_in_repos
        if self.codenotary_enabled:
            packages_mapping = dict(await asyncio.gather(*authenticate_tasks))

        for package_dict in release.plan['packages']:
            package = package_dict['package']
            pkg_full_name = package['full_name']
            force_flag = package.get('force', False)
            force_not_notarized = package.get('force_not_notarized', False)
            if (
                self.codenotary_enabled
                and not packages_mapping[package['sha256']]
                and not force_not_notarized
            ):
                raise ReleaseLogicError(
                    f'Cannot release {pkg_full_name}, '
                    'package is not authenticated by CAS'
                )
            existing_repo_ids = pkgs_in_repos.get(pkg_full_name, ())
            package_href = package['href_from_repo']
            # if force release is enabled for package,
            # we should release package from build repo
            if force_flag or package_href is None:
                package_href = package['artifact_href']
            for repository in package_dict['repositories']:
                repo_id = repository['id']
                repo_name = repository['name']
                repo_arch = repository['arch']
                if repo_id in existing_repo_ids and not force_flag:
                    if package['href_from_repo'] is not None:
                        continue
                    full_repo_name = f"{repo_name}-{repo_arch}"
                    raise ReleaseLogicError(
                        f'Cannot release {pkg_full_name} in {full_repo_name}, '
                        'package already in repo and force release is disabled'
                    )
                if repo_name not in packages_to_repo_layout:
                    packages_to_repo_layout[repo_name] = {}
                if repo_arch not in packages_to_repo_layout[repo_name]:
                    packages_to_repo_layout[repo_name][repo_arch] = []
                packages_to_repo_layout[repo_name][repo_arch].append(
                    package_href)

        prod_repo_modules_cache = {}
        added_modules = defaultdict(list)
        for module in release.plan.get('modules', []):
            for repository in module['repositories']:
                repo_name = repository['name']
                repo_arch = repository['arch']
                repo_url = repository.get('url')
                if repo_url is None:
                    repo_url = next(
                        repo.url for repo in self.base_platform.repos
                        if repo.name == repo_name and repo.arch == repo_arch
                        and repo.debug is False
                    )
                repo_module_index = prod_repo_modules_cache.get(repo_url)
                if repo_module_index is None:
                    template = await self.pulp_client.get_repo_modules_yaml(
                        repo_url)
                    if not template:
                        repo_module_index = IndexWrapper.from_template(template)
                    else:
                        repo_module_index = IndexWrapper()
                    prod_repo_modules_cache[repo_url] = repo_module_index
                if repo_name not in packages_to_repo_layout:
                    packages_to_repo_layout[repo_name] = {}
                if repo_arch not in packages_to_repo_layout[repo_name]:
                    packages_to_repo_layout[repo_name][repo_arch] = []
                module_info = module['module']
                release_module = ModuleWrapper.from_template(
                    module_info['template'])
                release_module_nvsca = release_module.nsvca
                full_repo_name = f"{repo_name}-{repo_arch}"
                # for old module releases that have duplicated repos
                if release_module_nvsca in added_modules[full_repo_name]:
                    continue
                module_already_in_repo = any((
                    prod_module
                    for prod_module in repo_module_index.iter_modules()
                    if prod_module.nsvca == release_module_nvsca
                ))
                if module_already_in_repo:
                    additional_messages.append(
                        f'Module {release_module_nvsca} skipped,'
                        f'module already in "{full_repo_name}" modules.yaml'
                    )
                    continue
                module_pulp_href, _ = await self.pulp_client.create_module(
                    module_info['template'],
                    module_info['name'],
                    module_info['stream'],
                    module_info['context'],
                    module_info['arch']
                )
                packages_to_repo_layout[repo_name][repo_arch].append(
                    module_pulp_href)
                added_modules[full_repo_name].append(release_module_nvsca)

        modify_tasks = []
        publication_tasks = []
        for repository_name, arches in packages_to_repo_layout.items():
            for arch, packages in arches.items():
                # TODO: we already have all repos in self.base_platform.repos,
                #   we can store them in dict
                #   for example: (repo_name, arch): repo
                repo_q = select(models.Repository).where(
                    models.Repository.name == repository_name,
                    models.Repository.arch == arch
                )
                repo_result = await self.db.execute(repo_q)
                repo: models.Repository = repo_result.scalars().first()
                if not repo:
                    raise MissingRepository(
                        f'Repository with name {repository_name} is missing '
                        f'or doesn\'t have pulp_href field')
                modify_tasks.append(self.pulp_client.modify_repository(
                    repo.pulp_href, add=packages))
                # after modify repo we need to publish repo content
                publication_tasks.append(
                    self.pulp_client.create_rpm_publication(repo.pulp_href))
        await asyncio.gather(*modify_tasks)
        await asyncio.gather(*publication_tasks)
        return additional_messages

    async def check_released_errata_packages(
        self,
        release: models.Release,
    ):
        if release.status != ReleaseStatus.COMPLETED:
            return
        package_hrefs = [
            package['package']['artifact_href']
            for package in release.plan['packages']
        ]
        subquery = select(models.BuildTaskArtifact.id).where(
            models.BuildTaskArtifact.href.in_(package_hrefs)
        ).scalar_subquery()
        albs_pkgs = await self.db.execute(
            select(models.ErrataToALBSPackage)
            .where(or_(
                models.ErrataToALBSPackage.albs_artifact_id.in_(subquery),
                models.ErrataToALBSPackage.pulp_href.in_(package_hrefs),
            ))
        )
        for albs_pkg in albs_pkgs.scalars().all():
            albs_pkg.status = ErrataPackageStatus.released
        await self.db.commit()

    async def update_release_plan(
            self, plan: dict,
            release: models.Release,
    ) -> dict:
        updated_plan = plan.copy()
        self.base_platform = release.platform
        for pkg_dict in plan['packages']:
            package = pkg_dict['package']
            is_debug = is_debuginfo_rpm(package['name'])
            await self.prepare_data_for_executing_async_tasks(
                package, is_debug)
        (
            pkgs_from_repos, pkgs_in_repos
        ) = await self.prepare_and_execute_async_tasks(plan['packages'])
        updated_plan['packages_from_repos'] = pkgs_from_repos
        updated_plan['packages_in_repos'] = pkgs_in_repos
        return updated_plan

    async def commit_release(
        self,
        release_id: int,
        user_id: int,
    ) -> typing.Tuple[models.Release, str]:
        release, message = await super().commit_release(release_id, user_id)
        await self.check_released_errata_packages(release)
        return release, message


def get_releaser_class(
        product: models.Product
) -> typing.Union[typing.Type[CommunityReleasePlanner],
                  typing.Type[AlmaLinuxReleasePlanner]]:
    if product.is_community:
        return CommunityReleasePlanner
    return AlmaLinuxReleasePlanner

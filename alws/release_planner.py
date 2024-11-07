import asyncio
import copy
import datetime
import logging
import re
import traceback
import typing
from abc import ABCMeta, abstractmethod
from collections import defaultdict

from immudb_wrapper import ImmudbWrapper
from sqlalchemy import or_, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.orm import selectinload

from alws import models
from alws.config import settings
from alws.constants import (
    LOWEST_PRIORITY,
    BeholderKey,
    BeholderMatchMethod,
    ErrataPackageStatus,
    ErrataReleaseStatus,
    PackageNevra,
    ReleasePackageTrustness,
    ReleaseStatus,
    RepoType,
)
from alws.crud import products as product_crud
from alws.crud import sign_task
from alws.crud import user as user_crud
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
from alws.pulp_models import RpmPackage
from alws.schemas import release_schema
from alws.utils.beholder_client import BeholderClient
from alws.utils.debuginfo import clean_debug_name, is_debuginfo_rpm
from alws.utils.github_integration_helper import (
    close_issues,
)
from alws.utils.measurements import class_measure_work_time_async
from alws.utils.modularity import IndexWrapper, ModuleWrapper
from alws.utils.parsing import get_clean_distr_name
from alws.utils.pulp_client import PulpClient
from alws.utils.pulp_utils import (
    get_rpm_packages_by_ids,
    get_rpm_packages_from_repositories,
    get_rpm_packages_from_repository,
    get_uuid_from_pulp_href,
)

__all__ = [
    "CommunityReleasePlanner",
    "AlmaLinuxReleasePlanner",
    "get_releaser_class",
]


class BaseReleasePlanner(metaclass=ABCMeta):
    def __init__(self, db: AsyncSession):
        self._db = db
        self.pulp_client = PulpClient(
            settings.pulp_host,
            settings.pulp_user,
            settings.pulp_password,
        )
        self.codenotary_enabled = settings.codenotary_enabled
        if self.codenotary_enabled:
            self._immudb_wrapper = ImmudbWrapper(
                username=settings.immudb_username,
                password=settings.immudb_password,
                database=settings.immudb_database,
                immudb_address=settings.immudb_address,
                public_key_file=settings.immudb_public_key_file,
            )
        self.stats = {}

    async def revert_release(
        self,
        release_id: int,
        user_id: int,
    ):
        message = "Successfully reverted release"
        logging.info("Start reverting release: %d", release_id)
        user = await user_crud.get_user(self.db, user_id=user_id)
        release = await self.get_release_for_update(release_id)
        if not release:
            raise DataNotFoundError(f"{release_id=} not found")

        if not can_perform(release, user, actions.ReleaseToProduct.name):
            raise PermissionDenied(
                "User does not have permissions to update release"
            )
        try:
            await self.revert_release_plan(release)
        except Exception as e:
            message = f"Cannot revert release:\n{traceback.format_exc()}"
            release.status = ReleaseStatus.FAILED
            logging.exception("Cannot revert release: %d", release_id)
            raise e
        # for updating release plan, we should use deepcopy
        release_plan = copy.deepcopy(release.plan)
        release_plan["last_log"] = message
        release.plan = release_plan
        await self.db.flush()
        logging.info("Successfully reverted release: %s", release_id)

    async def remove_packages_from_repositories(
        self,
        release: models.Release,
    ) -> typing.Tuple[typing.List[str], typing.List[str]]:
        pkgs_to_remove = []
        repo_ids_to_remove = []
        for pkg_dict in release.plan.get("packages", []):
            pkg_href = pkg_dict.get("package", {}).get("artifact_href", "")
            repo_ids = [repo["id"] for repo in pkg_dict.get("repositories", [])]
            if not pkg_href or not repo_ids:
                continue
            pkgs_to_remove.append(pkg_href)
            repo_ids_to_remove.extend(repo_ids)

        db_repos = await self.db.execute(
            select(models.Repository).where(
                models.Repository.id.in_(repo_ids_to_remove),
            )
        )
        modify_tasks = []
        publish_tasks = []
        for repo in db_repos.scalars().all():
            modify_tasks.append(
                self.pulp_client.modify_repository(
                    repo.pulp_href,
                    remove=pkgs_to_remove,
                )
            )
            publish_tasks.append(
                self.pulp_client.create_rpm_publication(repo.pulp_href),
            )
        await asyncio.gather(*modify_tasks)
        await asyncio.gather(*publish_tasks)
        return pkgs_to_remove, repo_ids_to_remove

    async def revert_release_plan(
        self,
        release: models.Release,
    ):
        raise NotImplementedError()

    @property
    def db(self):
        return self._db

    @abstractmethod
    async def get_release_plan(
        self,
        base_platform: models.Platform,
        build_ids: typing.List[int],
        build_tasks: typing.Optional[typing.List[int]] = None,
        product: typing.Optional[models.Product] = None,
    ) -> dict:
        raise NotImplementedError()

    @abstractmethod
    async def update_release_plan(
        self,
        plan: dict,
        release: models.Release,
    ) -> dict:
        raise NotImplementedError()

    @abstractmethod
    async def execute_release_plan(
        self,
        release: models.Release,
    ) -> typing.List[str]:
        raise NotImplementedError()

    @staticmethod
    def is_beta_build(build: models.Build) -> bool:
        return False

    @staticmethod
    def is_debug_repository(repo_name: str) -> bool:
        return bool(re.search(r"debug(info|source|)", repo_name))

    async def authenticate_package(self, package_checksum: str):
        is_authenticated = False
        if self.codenotary_enabled:
            response = self._immudb_wrapper.authenticate(
                package_checksum,
            )
            is_authenticated = response.get('verified', False)
        return package_checksum, is_authenticated

    @class_measure_work_time_async("get_packages_info_pulp_api")
    async def get_pulp_packages_info(
        self,
        build_rpms: typing.List[
            typing.Union[models.SourceRpm, models.BinaryRpm]
        ],
        build_tasks: typing.Optional[typing.List[int]] = None,
    ) -> typing.List[typing.Dict[str, typing.Any]]:
        packages_fields = [
            RpmPackage.content_ptr_id,
            RpmPackage.name,
            RpmPackage.epoch,
            RpmPackage.version,
            RpmPackage.release,
            RpmPackage.arch,
        ]
        pulp_packages = get_rpm_packages_by_ids(
            [
                get_uuid_from_pulp_href(rpm.artifact.href)
                for rpm in build_rpms
                if build_tasks and rpm.artifact.build_task_id in build_tasks
            ],
            packages_fields,
        )
        return [
            {
                "name": package.name,
                "epoch": package.epoch,
                "version": package.version,
                "release": package.release,
                "arch": package.arch,
                "pulp_href": package.pulp_href,
                "sha256": package.sha256,
            }
            for _, package in pulp_packages.items()
        ]

    @class_measure_work_time_async("get_packages_info_pulp_and_db")
    async def get_pulp_packages(
        self,
        build_ids: typing.List[int],
        platform_id: int,
        build_tasks: typing.Optional[typing.List[int]] = None,
    ) -> typing.Tuple[typing.List[dict], typing.List[str], typing.List[dict]]:
        src_rpm_names = []
        pulp_packages = []

        builds_q = (
            select(models.Build)
            .where(models.Build.id.in_(build_ids))
            .options(
                selectinload(models.Build.platform_flavors),
                selectinload(models.Build.source_rpms)
                .selectinload(models.SourceRpm.artifact)
                .selectinload(models.BuildTaskArtifact.build_task),
                selectinload(models.Build.binary_rpms)
                .selectinload(models.BinaryRpm.artifact)
                .selectinload(models.BuildTaskArtifact.build_task),
                selectinload(models.Build.binary_rpms)
                .selectinload(models.BinaryRpm.source_rpm)
                .selectinload(models.SourceRpm.artifact),
                selectinload(models.Build.tasks).selectinload(
                    models.BuildTask.rpm_modules
                ),
                selectinload(models.Build.repos),
            )
        )
        build_result = await self.db.execute(builds_q)
        modules_to_release = defaultdict(dict)
        for build in build_result.scalars().all():
            build_rpms = [
                build_rpm
                for rpms_list in [
                    build.source_rpms,
                    build.binary_rpms,
                ]
                for build_rpm in rpms_list
                if build_rpm.artifact.build_task.platform_id == platform_id
            ]
            logging.info('Build RPMs "%s"', build_rpms)
            pulp_artifacts = await self.get_pulp_packages_info(
                build_rpms,
                build_tasks,
            )
            pulp_artifacts = {
                artifact_dict.pop("pulp_href"): artifact_dict
                for artifact_dict in pulp_artifacts
            }
            for rpm in build_rpms:
                artifact_task_id = rpm.artifact.build_task_id
                if build_tasks and artifact_task_id not in build_tasks:
                    continue
                artifact_name = rpm.artifact.name
                source_name = None
                pkg_info = copy.deepcopy(pulp_artifacts[rpm.artifact.href])
                pkg_info["is_beta"] = self.is_beta_build(build)
                pkg_info["build_id"] = build.id
                pkg_info["artifact_href"] = rpm.artifact.href
                pkg_info["cas_hash"] = rpm.artifact.cas_hash
                pkg_info["href_from_repo"] = None
                pkg_info["full_name"] = artifact_name
                build_task = next(
                    task for task in build.tasks if task.id == artifact_task_id
                )
                pkg_info["task_arch"] = build_task.arch
                pkg_info["force"] = False
                pkg_info["force_not_notarized"] = False
                source_rpm = getattr(rpm, "source_rpm", None)
                if source_rpm:
                    source_name = source_rpm.artifact.name
                if ".src.rpm" in artifact_name:
                    src_rpm_names.append(artifact_name)
                    source_name = artifact_name
                pkg_info["source"] = source_name
                pulp_packages.append(pkg_info)

            for task in build.tasks:
                skip_modules_processing = True
                if task.rpm_modules and task.id in build_tasks:
                    for module in task.rpm_modules:
                        key = (
                            module.name,
                            module.stream,
                            module.version,
                            module.arch,
                        )
                        if key not in modules_to_release:
                            skip_modules_processing = False
                    if skip_modules_processing:
                        continue
                    module_repo = next(
                        build_repo
                        for build_repo in task.build.repos
                        if build_repo.arch == task.arch
                        and not build_repo.debug
                        and build_repo.type == "rpm"
                        and build_repo.platform_id == platform_id
                    )
                    template = await self.pulp_client.get_repo_modules_yaml(
                        module_repo.url
                    )
                    module_index = IndexWrapper()
                    if template:
                        module_index = IndexWrapper.from_template(template)
                    for module in module_index.iter_modules():
                        key = (
                            module.name,
                            module.stream,
                            str(module.version),
                            module.arch,
                        )
                        # in some cases we have also devel module in template,
                        # we should add all modules from template
                        modules_to_release[key] = {
                            "build_id": build.id,
                            "name": module.name,
                            "stream": module.stream,
                            # Module version needs to be converted into
                            # string because it's going to be involved later
                            # in release plan. When interacting with API
                            # via Swagger or albs-frontend, we'll loose
                            # precision as described here:
                            # https://github.com/tiangolo/fastapi/issues/2483#issuecomment-744576007
                            "version": str(module.version),
                            "context": module.context,
                            "arch": module.arch,
                            "template": module.render(),
                        }

        pulp_rpm_modules = list(modules_to_release.values())
        return pulp_packages, src_rpm_names, pulp_rpm_modules

    async def get_final_release(self, release_id: int) -> models.Release:
        release_res = await self.db.execute(
            select(models.Release)
            .where(models.Release.id == release_id)
            .options(
                selectinload(models.Release.owner),
                selectinload(models.Release.platform),
                selectinload(models.Release.product),
                selectinload(models.Release.performance_stats),
            )
        )
        return release_res.scalars().first()

    async def get_release_for_update(
        self,
        release_id: int,
    ) -> typing.Optional[models.Release]:
        query = (
            select(models.Release)
            .where(models.Release.id == release_id)
            .options(
                selectinload(models.Release.owner),
                selectinload(models.Release.owner).selectinload(
                    models.User.oauth_accounts
                ),
                selectinload(models.Release.owner)
                .selectinload(models.User.roles)
                .selectinload(models.UserRole.actions),
                selectinload(models.Release.owner).selectinload(
                    models.User.oauth_accounts
                ),
                selectinload(models.Release.team)
                .selectinload(models.Team.roles)
                .selectinload(models.UserRole.actions),
                selectinload(models.Release.platform).selectinload(
                    models.Platform.reference_platforms
                ),
                selectinload(models.Release.platform).selectinload(
                    models.Platform.repos.and_(
                        models.Repository.production.is_(True),
                    ),
                ),
                selectinload(models.Release.product).selectinload(
                    models.Product.repositories
                ),
                selectinload(models.Release.product).selectinload(
                    models.Product.builds
                ),
                selectinload(models.Release.performance_stats),
            )
            .with_for_update()
        )
        release_result = await self.db.execute(query)
        release = release_result.scalars().first()
        return release

    @class_measure_work_time_async("create_new_release")
    async def create_new_release(
        self,
        user_id: int,
        payload: release_schema.ReleaseCreate,
    ) -> models.Release:
        start = datetime.datetime.utcnow()
        user = await user_crud.get_user(self.db, user_id=user_id)
        logging.info("User %d is creating a release", user_id)

        platform = await self.db.execute(
            select(models.Platform)
            .where(
                models.Platform.id == payload.platform_id,
            )
            .options(
                selectinload(models.Platform.reference_platforms),
                selectinload(
                    models.Platform.repos.and_(
                        models.Repository.production.is_(True)
                    )
                ),
                selectinload(models.Platform.roles).selectinload(
                    models.UserRole.actions
                ),
            ),
        )
        platform = platform.scalars().first()
        product = await product_crud.get_products(
            self.db,
            product_id=payload.product_id,
        )
        builds = (
            (
                await self.db.execute(
                    select(models.Build)
                    .where(models.Build.id.in_(payload.builds))
                    .options(
                        selectinload(models.Build.team)
                        .selectinload(models.Team.roles)
                        .selectinload(models.UserRole.actions),
                        selectinload(models.Build.owner)
                        .selectinload(models.User.roles)
                        .selectinload(models.UserRole.actions),
                    )
                )
            )
            .scalars()
            .all()
        )

        for build in builds:
            if not can_perform(build, user, actions.ReleaseBuild.name):
                raise PermissionDenied(
                    "User does not have permissions to release build"
                    f" {build.id}"
                )

        if not can_perform(product, user, actions.ReleaseToProduct.name):
            raise PermissionDenied(
                "User does not have permissions to release to this product"
            )

        new_release = models.Release()
        new_release.build_ids = payload.builds
        if getattr(payload, "build_tasks", None):
            new_release.build_task_ids = payload.build_tasks
        new_release.platform = platform
        new_release.plan = await self.get_release_plan(
            base_platform=platform,
            build_ids=payload.builds,
            build_tasks=payload.build_tasks,
            product=product,
        )
        new_release.owner = user
        new_release.team_id = product.team_id
        new_release.product_id = product.id
        new_release.started_at = start
        new_release.finished_at = datetime.datetime.utcnow()
        self.db.add(new_release)
        await self.db.flush()
        await self.db.refresh(new_release)

        logging.info("New release %d successfully created", new_release.id)
        return await self.get_final_release(new_release.id)

    @class_measure_work_time_async("update_release")
    async def update_release(
        self,
        release_id: int,
        payload: release_schema.ReleaseUpdate,
        user_id: int,
    ) -> models.Release:
        logging.info("Updating release %d", release_id)
        user = await user_crud.get_user(self.db, user_id=user_id)

        release = await self.get_release_for_update(release_id)
        if not release:
            raise DataNotFoundError(f"Release with ID {release_id} not found")

        if not can_perform(release, user, actions.ReleaseToProduct.name):
            raise PermissionDenied(
                "User does not have permissions to update release"
            )

        release.started_at = datetime.datetime.utcnow()
        build_tasks = getattr(payload, "build_tasks", None)
        if (payload.builds and payload.builds != release.build_ids) or (
            build_tasks and build_tasks != release.build_task_ids
        ):
            release.build_ids = payload.builds
            if build_tasks:
                release.build_task_ids = payload.build_tasks
            release.plan = await self.get_release_plan(
                base_platform=release.platform,
                build_ids=payload.builds,
                build_tasks=payload.build_tasks,
                product=release.product,
            )
        elif payload.plan:
            # TODO: Add packages presence check in community repos
            new_plan = await self.update_release_plan(payload.plan, release)
            release.plan = new_plan
        release.finished_at = datetime.datetime.utcnow()
        self.db.add(release)
        await self.db.flush()
        await self.db.refresh(release)
        logging.info("Successfully updated release %d", release_id)
        return await self.get_final_release(release.id)

    @class_measure_work_time_async("commit_release")
    async def commit_release(
        self,
        release_id: int,
        user_id: int,
    ) -> typing.Tuple[models.Release, str]:
        logging.info("Committing release %d", release_id)

        user = await user_crud.get_user(self.db, user_id=user_id)
        release = await self.get_release_for_update(release_id)
        if not release:
            raise DataNotFoundError(f"Release with ID {release_id} not found")

        if not can_perform(release, user, actions.ReleaseToProduct.name):
            raise PermissionDenied(
                "User does not have permissions to commit the release"
            )

        release.started_at = datetime.datetime.utcnow()
        builds_released = False
        try:
            release_messages = await self.execute_release_plan(release)
        except (
            EmptyReleasePlan,
            MissingRepository,
            SignError,
            ReleaseLogicError,
        ) as e:
            message = f"Cannot commit release: {str(e)}"
            release.status = ReleaseStatus.FAILED
        except Exception:
            message = f"Cannot commit release:\n{traceback.format_exc()}"
            release.status = ReleaseStatus.FAILED
        else:
            message = "Successfully committed release"
            if release_messages:
                message += "\nWARNING:\n"
                message += "\n".join(release_messages)
            release.status = ReleaseStatus.COMPLETED
            builds_released = True
            if settings.github_integration_enabled:
                try:
                    await close_issues(build_ids=release.build_ids)
                except Exception as err:
                    logging.exception(
                        "Cannot move issue to the Released section: %s",
                        err,
                    )

        await self.db.execute(
            update(models.Build)
            .where(models.Build.id.in_(release.build_ids))
            .values(release_id=release.id, released=builds_released)
        )
        # for updating release plan, we should use deepcopy
        release_plan = copy.deepcopy(release.plan)
        release_plan["last_log"] = message
        release.plan = release_plan
        release.finished_at = datetime.datetime.utcnow()
        self.db.add(release)
        await self.db.flush()
        await self.db.refresh(release)
        logging.info("Successfully committed release %d", release_id)
        release = await self.get_final_release(release_id)
        return release, message


class CommunityReleasePlanner(BaseReleasePlanner):
    @class_measure_work_time_async("revert_release_plan")
    async def revert_release_plan(
        self,
        release: models.Release,
    ):
        await self.remove_packages_from_repositories(release)
        await self.db.execute(
            update(models.Build)
            .where(
                models.Build.id.in_(release.build_ids),
                models.Build.release_id == release.id,
            )
            .values(
                release_id=None,
                released=False,
            )
        )
        release.product.builds = [
            build
            for build in release.product.builds
            if build.id not in release.build_ids
        ]
        release.status = ReleaseStatus.REVERTED

    @staticmethod
    def get_repo_pretty_name(repo_name: str) -> str:
        regex = re.compile(
            r"-(i686|x86_64|aarch64|ppc64le|s390x|src)(?P<debug>-debug)?-dr$"
        )
        pretty_name = regex.sub("", repo_name)
        debug_part = regex.search(repo_name)
        if debug_part and debug_part["debug"]:
            pretty_name += debug_part["debug"]
        return pretty_name

    @staticmethod
    def get_production_repositories_mapping(
        product: models.Product,
        include_pulp_href: bool = False,
        platform_name: str = "",
    ) -> dict:
        result = {}

        for repo in product.repositories:
            pretty_name = CommunityReleasePlanner.get_repo_pretty_name(
                repo.name,
            )
            if not re.search(
                rf"{platform_name}(-debug)?$",
                pretty_name,
                # We get lowered platform_name and some old repos
                # contain camel case platform in repo names
                re.IGNORECASE,
            ):
                continue
            main_info = {
                "id": repo.id,
                "name": pretty_name,
                "url": repo.url,
                "arch": repo.arch,
                "debug": repo.debug,
            }
            if include_pulp_href:
                main_info["pulp_href"] = repo.pulp_href
            result[(repo.arch, repo.debug)] = main_info

        return result

    @class_measure_work_time_async("get_release_plan")
    async def get_release_plan(
        self,
        base_platform: models.Platform,
        build_ids: typing.List[int],
        build_tasks: typing.Optional[typing.List[int]] = None,
        product: typing.Optional[models.Product] = None,
    ) -> dict:
        release_plan = {"modules": {}}
        added_packages = set()

        db_repos_mapping = self.get_production_repositories_mapping(
            product,
            platform_name=base_platform.name.lower(),
        )
        if not db_repos_mapping:
            raise ValueError("There is no matched repositories")

        (
            pulp_packages,
            src_rpm_names,
            pulp_rpm_modules,
        ) = await self.get_pulp_packages(
            build_ids,
            platform_id=base_platform.id,
            build_tasks=build_tasks,
        )

        release_plan["repositories"] = list(db_repos_mapping.values())

        plan_packages = []
        builds = await self.db.execute(
            select(models.Build)
            .where(models.Build.id.in_(build_ids))
            .options(selectinload(models.Build.repos))
        )
        i686_pkgs_in_x86_64_repos = []
        x86_64_build_repos_ids = [
            get_uuid_from_pulp_href(repo.pulp_href)
            for build in builds.scalars().all()
            for repo in build.repos
            if repo.arch == "x86_64"
        ]
        for repo_id in x86_64_build_repos_ids:
            for rpm_pkg in get_rpm_packages_from_repository(
                repo_id,
                pkg_arches=["i686"],
            ):
                i686_pkgs_in_x86_64_repos.append(rpm_pkg.pulp_href)
        for pkg in pulp_packages:
            if pkg["full_name"] in added_packages:
                continue
            is_debug = is_debuginfo_rpm(pkg["full_name"])
            arch = pkg["arch"]
            if arch == "noarch":
                repositories = [
                    db_repos_mapping[(a, is_debug)]
                    for a in base_platform.arch_list
                ]
            else:
                repositories = [db_repos_mapping[(arch, is_debug)]]
            repo_arch_location = [arch]
            if (
                arch == "i686"
                and pkg["artifact_href"] in i686_pkgs_in_x86_64_repos
            ):
                repo_arch_location.append("x86_64")
            if arch == "noarch":
                repo_arch_location = base_platform.arch_list
            plan_packages.append({
                "package": pkg,
                "repositories": repositories,
                "repo_arch_location": repo_arch_location,
            })
            added_packages.add(pkg["full_name"])
        release_plan["packages"] = plan_packages

        if pulp_rpm_modules:
            plan_modules = []
            for module in pulp_rpm_modules:
                # Modules go only in non-debug repos
                repository = db_repos_mapping[(module["arch"], False)]
                plan_modules.append(
                    {"module": module, "repositories": [repository]}
                )
            release_plan["modules"] = plan_modules

        return release_plan

    @class_measure_work_time_async("update_release_plan")
    async def update_release_plan(
        self,
        plan: dict,
        release: models.Release,
    ) -> dict:
        # We do not need to take additional actions for release update
        # right now
        return plan

    @class_measure_work_time_async("execute_release_plan")
    async def execute_release_plan(
        self,
        release: models.Release,
    ) -> typing.List[str]:
        additional_messages = []
        if not release.plan.get("packages") or not release.plan.get(
            "repositories"
        ):
            raise EmptyReleasePlan(
                "Cannot execute plan with empty packages or repositories: "
                "{packages}, {repositories}".format_map(release.plan)
            )

        repository_modification_mapping = defaultdict(list)
        db_repos_mapping = self.get_production_repositories_mapping(
            release.product,
            include_pulp_href=True,
            platform_name=release.platform.name.lower(),
        )

        for pkg in release.plan.get("packages", []):
            package = pkg["package"]
            for repository in pkg["repositories"]:
                repo_key = (repository["arch"], repository["debug"])
                db_repo = db_repos_mapping[repo_key]
                repository_modification_mapping[db_repo["pulp_href"]].append(
                    package["artifact_href"]
                )

        # TODO: Add support for checking existent packages in repos
        prod_repo_modules_cache = {}
        added_modules = defaultdict(list)
        for module in release.plan.get("modules", []):
            for repository in module["repositories"]:
                repo_name = repository["name"]
                repo_arch = repository["arch"]
                repo_url = repository.get("url")
                db_repo = db_repos_mapping[(repo_arch, False)]
                if not repo_url:
                    repo_url = db_repo["url"]
                repo_module_index = prod_repo_modules_cache.get(repo_url)
                if repo_module_index is None:
                    template = await self.pulp_client.get_repo_modules_yaml(
                        repo_url
                    )
                    repo_module_index = IndexWrapper()
                    if template:
                        repo_module_index = IndexWrapper.from_template(template)
                    prod_repo_modules_cache[repo_url] = repo_module_index
                module_info = module["module"]
                release_module = ModuleWrapper.from_template(
                    module_info["template"]
                )
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
                        f'Module {release_module_nvsca} skipped, '
                        f'module already in "{full_repo_name}" modules.yaml'
                    )
                    continue

                module_pulp_hrefs = await self.pulp_client.get_modules(
                    name=module_info["name"],
                    stream=module_info["stream"],
                    version=module_info['version'],
                    context=module_info["context"],
                    arch=module_info["arch"],
                    fields="pulp_href",
                    use_next=False,
                )
                # We assume there's only one module with the same module
                # nsvca in pulp.
                module_pulp_href = module_pulp_hrefs[0]['pulp_href']
                repository_modification_mapping[db_repo["pulp_href"]].append(
                    module_pulp_href
                )
                added_modules[full_repo_name].append(release_module_nvsca)

        await asyncio.gather(*(
            self.pulp_client.modify_repository(href, add=packages)
            for href, packages in repository_modification_mapping.items()
        ))
        await asyncio.gather(*(
            self.pulp_client.create_rpm_publication(href)
            for href in repository_modification_mapping.keys()
        ))
        builds = await self.db.execute(
            select(models.Build).where(
                models.Build.id.in_(release.build_ids),
            )
        )
        for build in builds.scalars().all():
            release.product.builds.append(build)

        return additional_messages


class AlmaLinuxReleasePlanner(BaseReleasePlanner):
    def __init__(self, db: AsyncSession):
        super().__init__(db)
        self.base_platform = None
        self.clean_base_dist_name_lower = None
        self.repo_name_regex = re.compile(
            r"\w+-(\w+-|)+\d+-(beta-|)(?P<name>\w+(-\w+)?)",
        )
        self._beholder_client = BeholderClient(settings.beholder_host)

    @staticmethod
    def is_beta_build(build: models.Build):
        if not hasattr(build, "platform_flavors"):
            return False
        if not build.platform_flavors:
            return False
        # Search for beta flavor
        found = False
        for flavor in build.platform_flavors:
            if bool(re.search(r"(-beta)$", flavor.name, re.IGNORECASE)):
                found = True
                break
        return found

    @class_measure_work_time_async("revert_release_plan_execution")
    async def revert_release_plan(
        self,
        release: models.Release,
    ):
        pkgs_to_remove, _ = await self.remove_packages_from_repositories(
            release,
        )
        subquery = (
            select(models.BuildTaskArtifact.id)
            .where(
                models.BuildTaskArtifact.href.in_(pkgs_to_remove),
            )
            .scalar_subquery()
        )
        errata_pkgs = await self.db.execute(
            select(models.NewErrataToALBSPackage).where(
                or_(
                    models.NewErrataToALBSPackage.albs_artifact_id.in_(
                        subquery
                    ),
                    models.NewErrataToALBSPackage.pulp_href.in_(pkgs_to_remove),
                )
            )
        )
        for errata_pkg in errata_pkgs.scalars().all():
            errata_pkg.status = ErrataPackageStatus.proposal
        await self.db.execute(
            update(models.Build)
            .where(
                models.Build.id.in_(release.build_ids),
                models.Build.release_id == release.id,
            )
            .values(
                release_id=None,
                released=False,
            )
        )
        release.status = ReleaseStatus.REVERTED

    @class_measure_work_time_async("packages_presence_check")
    async def check_packages_presence_in_prod_repositories(
        self,
        packages_list: typing.List[typing.Dict[str, typing.Any]],
    ) -> typing.Tuple[
        typing.DefaultDict[str, typing.List[int]],
        typing.DefaultDict[str, typing.List[int]],
    ]:
        repo_mapping = {}
        for repo in self.base_platform.repos:
            pulp_repo_id = get_uuid_from_pulp_href(repo.pulp_href)
            repo_mapping[pulp_repo_id] = (repo.id, repo.arch)

        pkg_names = []
        pkg_epochs = []
        pkg_versions = []
        pkg_releases = []
        pkg_arches = []
        pkgs_mapping = {}
        for package_info in packages_list:
            package = package_info["package"]
            nevra = PackageNevra(
                package["name"],
                package["epoch"],
                package["version"],
                package["release"],
                package["arch"],
            )
            pkgs_mapping[nevra] = package["full_name"]
            for collection, key in (
                (pkg_names, "name"),
                (pkg_epochs, "epoch"),
                (pkg_versions, "version"),
                (pkg_releases, "release"),
                (pkg_arches, "arch"),
            ):
                collection.append(package[key])

        packages_presence_info = defaultdict(list)
        pulp_packages = get_rpm_packages_from_repositories(
            repo_ids=list(repo_mapping),
            pkg_names=pkg_names,
            pkg_epochs=pkg_epochs,
            pkg_versions=pkg_versions,
            pkg_releases=pkg_releases,
            pkg_arches=pkg_arches,
        )
        for pulp_pkg in pulp_packages:
            full_name = pkgs_mapping.get(
                PackageNevra(
                    pulp_pkg.name,
                    pulp_pkg.epoch,
                    pulp_pkg.version,
                    pulp_pkg.release,
                    pulp_pkg.arch,
                )
            )
            if full_name is None:
                continue
            for repo_id in pulp_pkg.repo_ids:
                repo_info = repo_mapping.get(repo_id)
                if not repo_info:
                    continue
                packages_presence_info[full_name].append(
                    (pulp_pkg.pulp_href, *repo_info),
                )

        packages_from_repos = defaultdict(list)
        packages_in_repos = defaultdict(list)
        for package_info in packages_list:
            package = package_info["package"]
            full_name = package["full_name"]
            presence_info = packages_presence_info.get(full_name)
            data = None
            pkg_presence_by_repo_arch = {}
            if presence_info is None:
                continue
            # if packages were founded in pulp prod repos with same NEVRA,
            # we should take their hrefs by priority arches from platform
            for href, repo_id, repo_arch in presence_info:
                packages_in_repos[full_name].append(repo_id)
                pkg_presence_by_repo_arch[repo_arch] = (href, repo_id)
            for repo_arch, repo_info in pkg_presence_by_repo_arch.items():
                if repo_arch == "i686":
                    continue
                if repo_arch in self.base_platform.copy_priority_arches:
                    data = repo_info
                    break
                data = repo_info
            if data is None:
                continue
            repo_pkg_href, repo_id = data
            package["href_from_repo"] = repo_pkg_href
            packages_from_repos[full_name] = repo_id

        return packages_from_repos, packages_in_repos

    def get_devel_repo_key(
        self,
        arch: str,
        is_debug: bool,
        task_arch: str = "",
        is_module: bool = False,
    ):
        repo_name = "-".join((
            self.clean_base_dist_name_lower,
            self.base_platform.distr_version,
            "devel-debuginfo" if is_debug else "devel",
        ))
        repo_arch = arch if arch == "src" else task_arch
        if is_module:
            repo_arch = arch
        return RepoType(repo_name, repo_arch, is_debug)

    def get_devel_repo(
        self,
        arch: str,
        is_debug: bool,
        repos_mapping: dict,
        task_arch: str = "",
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
            full_name = package["full_name"]
            package_arch = package["arch"]
            package.pop("is_beta")
            is_debug = is_debuginfo_rpm(package["name"])
            if full_name in added_packages:
                continue
            devel_repo = self.get_devel_repo(
                arch=package_arch,
                is_debug=is_debug,
                repos_mapping=repos_mapping,
                task_arch=package["task_arch"],
            )
            if devel_repo is None:
                logging.debug(
                    "Skipping package=%s, repositories is missing",
                    full_name,
                )
                continue
            repo_arch_location = [package_arch]
            if package_arch == "noarch":
                repo_arch_location = self.base_platform.arch_list
            packages.append({
                "package": package,
                "repositories": [devel_repo],
                "repo_arch_location": repo_arch_location,
            })
            added_packages.add(full_name)
        (
            pkgs_from_repos,
            pkgs_in_repos,
        ) = await self.check_packages_presence_in_prod_repositories(packages)

        return {
            "packages": packages,
            "repositories": prod_repos,
            "packages_from_repos": pkgs_from_repos,
            "packages_in_repos": pkgs_in_repos,
            "modules": rpm_modules,
        }

    @staticmethod
    def update_beholder_cache(
        beholder_cache: typing.Dict[BeholderKey, typing.Any],
        packages: typing.List[dict],
        strong_arches: dict,
        is_beta: bool,
        is_devel: bool,
        priority: int,
        matched: str,
    ):
        def generate_key(pkg_arch: str) -> BeholderKey:
            return BeholderKey(
                pkg["name"],
                pkg["version"],
                pkg_arch,
                is_beta,
                is_devel,
            )

        for pkg in packages:
            key = generate_key(pkg["arch"])
            pkg["priority"] = priority
            pkg["matched"] = matched
            pkg_repos = pkg.get('repositories', [])
            prev_pkg = beholder_cache.get(key, {})
            if pkg_repos:
                for repo in pkg['repositories']:
                    repo['name'] = re.sub(
                        r'^\w+-(\w+-|)+\d+-(beta-|)',
                        '',
                        repo['name'],
                    )
                    repo['priority'] = priority
                pkg['repositories'].extend([
                    repo
                    for repo in prev_pkg.get('repositories', [])
                    if repo not in pkg_repos
                ])
            beholder_cache[key] = pkg
            for weak_arch in strong_arches[pkg["arch"]]:
                second_key = generate_key(weak_arch)
                # if we've already found repos for i686 arch
                # we don't need to override them,
                # because there can be multilib info
                cache_item = beholder_cache.get(second_key, {})
                if (
                    cache_item.get("repositories", [])
                    and weak_arch == "i686"
                    and priority >= cache_item["priority"]
                ):
                    continue
                replaced_pkg = copy.deepcopy(pkg)
                for repo in replaced_pkg["repositories"]:
                    if repo["arch"] == pkg["arch"]:
                        repo["arch"] = weak_arch
                beholder_cache[second_key] = replaced_pkg

    def find_release_repos(
        self,
        pkg_name: str,
        pkg_version: str,
        pkg_arch: str,
        is_beta: bool,
        is_devel: bool,
        is_debug: bool,
        beholder_cache: typing.Dict[BeholderKey, typing.Any],
    ) -> typing.Set[typing.Tuple[RepoType, int, str]]:
        def generate_key(beta: bool) -> BeholderKey:
            return BeholderKey(
                pkg_name,
                pkg_version,
                pkg_arch,
                beta,
                is_devel,
            )

        release_repositories = set()
        beholder_key = generate_key(is_beta)
        logging.debug(
            "At find_release_repos - beholder_key: %s",
            str(beholder_key),
        )
        predicted_package = beholder_cache.get(beholder_key, {})
        # if we doesn't found info from stable/beta,
        # we can try to find info by opposite stable/beta flag
        if not predicted_package:
            beholder_key = generate_key(not is_beta)
            logging.debug(
                "Not predicted_package, beholder_key: %s",
                str(beholder_key),
            )
            predicted_package = beholder_cache.get(beholder_key, {})
        # if we doesn't found info by current version,
        # then we should try find info by other versions
        if not predicted_package:
            beholder_keys = [
                key
                for key in beholder_cache
                if (
                    pkg_name == key.name
                    and pkg_arch == key.arch
                    and is_devel == key.is_devel
                )
            ]
            logging.debug(
                "Still not predicted_package, beholder_keys: %s",
                str(beholder_keys),
            )
            predicted_package = next(
                (beholder_cache[key] for key in beholder_keys),
                {},
            )
        for repo in predicted_package.get("repositories", []):
            trustness: int = repo["priority"]
            matched: str = predicted_package["matched"]
            repo_name = repo["name"]
            # in cases if we try to find debug repos by non debug name
            if is_debug and not repo_name.endswith("debuginfo"):
                repo_name += "-debuginfo"
            release_repo_name = "-".join((
                self.clean_base_dist_name_lower,
                self.base_platform.distr_version,
                repo_name,
            ))
            release_repo = RepoType(release_repo_name, repo["arch"], is_debug)
            release_repositories.add((release_repo, trustness, matched))
        return release_repositories

    @staticmethod
    def _beholder_matched_to_priority(matched: str) -> int:
        priority = LOWEST_PRIORITY
        if matched in BeholderMatchMethod.green():
            priority = ReleasePackageTrustness.MAXIMUM.value
        elif matched in BeholderMatchMethod.yellow():
            priority = ReleasePackageTrustness.MEDIUM.value
        return priority

    @class_measure_work_time_async("get_release_plan")
    async def get_release_plan(
        self,
        build_ids: typing.List[int],
        base_platform: models.Platform,
        build_tasks: typing.Optional[typing.List[int]] = None,
        product: typing.Optional[models.Product] = None,
    ) -> dict:
        packages = []
        rpm_modules = []
        beholder_cache = {}
        repos_mapping = {}
        strong_arches = defaultdict(list)
        added_packages = set()
        prod_repos = []
        self.base_platform = base_platform

        (
            pulp_packages,
            src_rpm_names,
            pulp_rpm_modules,
        ) = await self.get_pulp_packages(
            build_ids,
            platform_id=base_platform.id,
            build_tasks=build_tasks,
        )

        clean_base_dist_name = get_clean_distr_name(base_platform.name)
        if clean_base_dist_name is None:
            raise ValueError(
                f"Base distribution name is malformed: {base_platform.name}"
            )
        self.clean_base_dist_name_lower = clean_base_dist_name.lower()

        for repo in base_platform.repos:
            repo_dict = {
                "id": repo.id,
                "name": repo.name,
                "arch": repo.arch,
                "debug": repo.debug,
                "url": repo.url,
            }
            repo_key = RepoType(repo.name, repo.arch, repo.debug)
            repos_mapping[repo_key] = repo_dict
            prod_repos.append(repo_dict)

        for weak_arch in base_platform.weak_arch_list:
            strong_arches[weak_arch["depends_on"]].append(weak_arch["name"])

        if not settings.package_beholder_enabled:
            rpm_modules = [
                {"module": module, "repositories": []} for module in rpm_modules
            ]
            return await self.get_pulp_based_response(
                pulp_packages=pulp_packages,
                rpm_modules=rpm_modules,
                repos_mapping=repos_mapping,
                prod_repos=prod_repos,
            )

        for module in pulp_rpm_modules:
            module_name = module["name"]
            module_stream = module["stream"]
            module_arch_list = [module["arch"]]
            module_nvsca = (
                f"{module_name}:{module['version']}:{module_stream}:"
                f"{module['context']}:{module['arch']}"
            )
            for strong_arch, weak_arches in strong_arches.items():
                if module["arch"] in weak_arches:
                    module_arch_list.append(strong_arch)

            platforms_list = base_platform.reference_platforms + [base_platform]
            module_responses = await self._beholder_client.retrieve_responses(
                platforms_list,
                module_name=module_name,
                module_stream=module_stream,
                module_arch_list=module_arch_list,
            )
            module_info = {"module": module, "repositories": []}
            if not module_responses:
                devel_repo = self.get_devel_repo(
                    arch=module["arch"],
                    is_debug=False,
                    repos_mapping=repos_mapping,
                    is_module=True,
                )
                if devel_repo is None:
                    logging.debug(
                        "Skipping module=%s, devel repo is missing",
                        module_nvsca,
                    )
                    continue
                module_info["repositories"].append(devel_repo)
            rpm_modules.append(module_info)
            matched = BeholderMatchMethod.EXACT.value
            for module_response in module_responses:
                distr = module_response["distribution"]
                is_beta = distr["version"].endswith("-beta")
                is_devel = module_response["name"].endswith("-devel")
                for _packages in module_response["artifacts"]:
                    self.update_beholder_cache(
                        beholder_cache,
                        _packages["packages"],
                        strong_arches,
                        is_beta,
                        is_devel,
                        module_response["priority"],
                        matched,
                    )
                trustness = module_response["priority"]
                module_repo = module_response["repository"]
                repo_name = self.repo_name_regex.search(
                    module_repo["name"]
                ).groupdict()["name"]
                release_repo_name = "-".join((
                    self.clean_base_dist_name_lower,
                    base_platform.distr_version,
                    repo_name,
                ))
                repo_key = RepoType(release_repo_name, module["arch"], False)
                prod_repo = repos_mapping.get(repo_key)
                if prod_repo is None:
                    prod_repo = self.get_devel_repo(
                        arch=module["arch"],
                        is_debug=False,
                        repos_mapping=repos_mapping,
                        is_module=True,
                    )
                    trustness = ReleasePackageTrustness.UNKNOWN
                    if prod_repo is None:
                        logging.debug(
                            "Skipping module=%s, devel repo is missing",
                            module_nvsca,
                        )
                        continue
                module_repo_dict = {
                    "name": repo_key.name,
                    "arch": repo_key.arch,
                    "debug": repo_key.debug,
                    "url": prod_repo["url"],
                    "trustness": trustness,
                    "matched": matched,
                }
                if module_repo_dict in module_info["repositories"]:
                    continue
                module_info["repositories"].append(module_repo_dict)

        platforms_list = base_platform.reference_platforms + [base_platform]
        beholder_responses = await self._beholder_client.retrieve_responses(
            platforms_list,
            data={
                "source_rpms": src_rpm_names,
                "match": BeholderMatchMethod.all(),
            },
        )

        for beholder_response in beholder_responses:
            distr = beholder_response["distribution"]
            is_beta = distr["version"].endswith("-beta")
            is_devel = False
            for pkg_list in beholder_response.get("packages", {}):
                # we should apply matches in reversed order
                # to overwrite less accurate results by more accurate
                # name_only -> name_version -> closest -> exact
                for matched in BeholderMatchMethod.all():
                    if matched not in pkg_list['packages'].keys():
                        continue
                    response_priority = self._beholder_matched_to_priority(
                        matched,
                    )
                    self.update_beholder_cache(
                        beholder_cache,
                        pkg_list["packages"][matched],
                        strong_arches,
                        is_beta,
                        is_devel,
                        response_priority,
                        matched,
                    )
        if not beholder_cache:
            return await self.get_pulp_based_response(
                pulp_packages=pulp_packages,
                rpm_modules=rpm_modules,
                repos_mapping=repos_mapping,
                prod_repos=prod_repos,
            )
        logging.debug("beholder_cache: %s", str(beholder_cache))
        logging.debug("pulp_packages: %s", str(pulp_packages))
        logging.debug("repos_mapping: %s", str(repos_mapping))
        for package in pulp_packages:
            pkg_name = package["name"]
            pkg_version = package["version"]
            pkg_arch = package["arch"]
            full_name = package["full_name"]
            is_beta = package.pop("is_beta")
            is_debug = is_debuginfo_rpm(pkg_name)
            if full_name in added_packages:
                continue
            release_repository_keys = set()
            release_repositories = set()
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
            if pkg_arch == "noarch":
                pulp_repo_arch_location = self.base_platform.arch_list
            pkg_info = {
                "package": package,
                "repositories": [],
                "repo_arch_location": pulp_repo_arch_location,
            }
            if not release_repository_keys:
                devel_repo = self.get_devel_repo(
                    arch=pkg_arch,
                    is_debug=is_debug,
                    repos_mapping=repos_mapping,
                    task_arch=package["task_arch"],
                )
                if devel_repo is None:
                    logging.debug(
                        "Skipping package=%s, devel repo is missing",
                        full_name,
                    )
                    continue
                devel_repo["trustness"] = ReleasePackageTrustness.UNKNOWN
                pkg_info["repositories"].append(devel_repo)
                packages.append(pkg_info)
                added_packages.add(full_name)
                continue
            noarch_repos = set()
            arches_by_repo_name = defaultdict(set)
            for (
                release_repo_key,
                trustness,
                matched,
            ) in release_repository_keys:
                release_repo = repos_mapping.get(release_repo_key)
                # in some cases we get repos that we can't match
                if release_repo is None:
                    release_repo_key = self.get_devel_repo_key(
                        arch=pkg_arch,
                        is_debug=is_debug,
                        task_arch=package["task_arch"],
                    )
                    release_repo = self.get_devel_repo(
                        arch=pkg_arch,
                        is_debug=is_debug,
                        repos_mapping=repos_mapping,
                        task_arch=package["task_arch"],
                    )
                    trustness = ReleasePackageTrustness.UNKNOWN
                    if not release_repo:
                        logging.debug(
                            "Skipping package=%s, devel repo is missing",
                            full_name,
                        )
                        continue
                release_repo["trustness"] = trustness
                release_repo["matched"] = matched
                repo_name = release_repo['name']
                repo_arch_location = [release_repo["arch"]]
                # we should add i686 arch for correct multilib showing in UI
                if pkg_arch == "i686" and "x86_64" in repo_arch_location:
                    repo_arch_location.append("i686")
                if pkg_arch == "noarch":
                    if release_repo["name"] in noarch_repos:
                        continue
                    noarch_repos.add(release_repo["name"])
                    repo_arch_location = pulp_repo_arch_location
                arches_by_repo_name[repo_name].update(repo_arch_location)
                release_repositories.add(release_repo_key)
            # for every repository we should add pkg_info
            # for correct package location in UI
            processed_repos = []
            for repo_key in release_repositories:
                repo = repos_mapping[repo_key]
                repo_name = repo['name']
                if repo_name in processed_repos:
                    continue
                copy_pkg_info = copy.deepcopy(pkg_info)
                copy_pkg_info.update({
                    # TODO: need to send only one repo instead of list
                    "repositories": [repo],
                    "repo_arch_location": list(arches_by_repo_name[repo_name]),
                })
                packages.append(copy_pkg_info)
                processed_repos.append(repo_name)
            added_packages.add(full_name)

        (
            pkgs_from_repos,
            pkgs_in_repos,
        ) = await self.check_packages_presence_in_prod_repositories(packages)
        return {
            "packages": packages,
            "packages_from_repos": pkgs_from_repos,
            "packages_in_repos": pkgs_in_repos,
            "modules": rpm_modules,
            "repositories": prod_repos,
        }

    @class_measure_work_time_async("execute_release_plan")
    async def execute_release_plan(
        self,
        release: models.Release,
    ) -> typing.List[str]:
        additional_messages = []
        authenticate_tasks = []
        packages_mapping = {}
        packages_to_repo_layout = {}
        if not release.plan.get("packages") or (
            not release.plan.get("repositories")
        ):
            raise EmptyReleasePlan(
                "Cannot execute plan with empty packages or repositories: "
                "{packages}, {repositories}".format_map(release.plan)
            )
        for build_id in release.build_ids:
            try:
                verified = await sign_task.verify_signed_build(
                    self.db, build_id, release.platform.id
                )
            except (DataNotFoundError, ValueError, SignError) as e:
                msg = f"The build {build_id} was not verified, because\n{e}"
                raise SignError(msg)
            if not verified:
                msg = f"Cannot execute plan with wrong singing of {build_id}"
                raise SignError(msg)

        # check packages presence in prod repos
        self.base_platform = release.platform
        for pkg_dict in release.plan["packages"]:
            package = pkg_dict["package"]
            if self.codenotary_enabled:
                authenticate_tasks.append(
                    self.authenticate_package(package["sha256"])
                )
        (
            pkgs_from_repos,
            pkgs_in_repos,
        ) = await self.check_packages_presence_in_prod_repositories(
            release.plan["packages"],
        )
        release.plan["packages_from_repos"] = pkgs_from_repos
        release.plan["packages_in_repos"] = pkgs_in_repos
        if self.codenotary_enabled:
            packages_mapping = dict(await asyncio.gather(*authenticate_tasks))

        for package_dict in release.plan["packages"]:
            package = package_dict["package"]
            pkg_full_name = package["full_name"]
            force_flag = package.get("force", False)
            force_not_notarized = package.get("force_not_notarized", False)
            if (
                self.codenotary_enabled
                and not packages_mapping[package["sha256"]]
                and not force_not_notarized
            ):
                raise ReleaseLogicError(
                    f"Cannot release {pkg_full_name}, "
                    "package is not authenticated by CAS"
                )
            existing_repo_ids = pkgs_in_repos.get(pkg_full_name, ())
            package_href = package["href_from_repo"]
            # if force release is enabled for package,
            # we should release package from build repo
            if force_flag or package_href is None:
                package_href = package["artifact_href"]
            for repository in package_dict["repositories"]:
                repo_id = repository["id"]
                repo_name = repository["name"]
                repo_arch = repository["arch"]
                if repo_id in existing_repo_ids and not force_flag:
                    if package["href_from_repo"] is not None:
                        continue
                    full_repo_name = f"{repo_name}-{repo_arch}"
                    raise ReleaseLogicError(
                        f"Cannot release {pkg_full_name} in {full_repo_name}, "
                        "package already in repo and force release is disabled"
                    )
                if repo_name not in packages_to_repo_layout:
                    packages_to_repo_layout[repo_name] = {}
                if repo_arch not in packages_to_repo_layout[repo_name]:
                    packages_to_repo_layout[repo_name][repo_arch] = []
                packages_to_repo_layout[repo_name][repo_arch].append(
                    package_href
                )

        prod_repo_modules_cache = {}
        added_modules = defaultdict(list)
        for module in release.plan.get("modules", []):
            for repository in module["repositories"]:
                repo_name = repository["name"]
                repo_arch = repository["arch"]
                repo_url = repository.get("url")
                if repo_url is None:
                    repo_url = next(
                        repo.url
                        for repo in self.base_platform.repos
                        if repo.name == repo_name
                        and repo.arch == repo_arch
                        and repo.debug is False
                    )
                repo_module_index = prod_repo_modules_cache.get(repo_url)
                if repo_module_index is None:
                    template = await self.pulp_client.get_repo_modules_yaml(
                        repo_url
                    )
                    repo_module_index = IndexWrapper()
                    if template:
                        repo_module_index = IndexWrapper.from_template(template)
                    prod_repo_modules_cache[repo_url] = repo_module_index
                if repo_name not in packages_to_repo_layout:
                    packages_to_repo_layout[repo_name] = {}
                if repo_arch not in packages_to_repo_layout[repo_name]:
                    packages_to_repo_layout[repo_name][repo_arch] = []
                module_info = module["module"]
                release_module = ModuleWrapper.from_template(
                    module_info["template"]
                )
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
                        f'Module {release_module_nvsca} skipped, '
                        f'module already in "{full_repo_name}" modules.yaml'
                    )
                    continue

                logging.info("module_info: %s", str(module_info))
                logging.info("release_module: %s", str(release_module))

                # I think that here we were having the "right behavior
                # by accident" after pulp migration.
                # Modules in release_plan might be getting a wrong final
                # module version. Not fake module one, but wrong due to
                # precision loss during their transit between back and front,
                # see: https://github.com/AlmaLinux/albs-web-server/commit/8ffea9a3ab41d93011e01f8464e1b767b1461bb4
                # Given that the module (with the right final version) already
                # exists in Pulp, all we need to do is to add such module to
                # the release repo at the end. This is, there's no need to
                # create a new module.
                module_pulp_hrefs = await self.pulp_client.get_modules(
                    name=module_info["name"],
                    stream=module_info["stream"],
                    version=module_info['version'],
                    context=module_info["context"],
                    arch=module_info["arch"],
                    fields="pulp_href",
                    use_next=False,
                )
                # We assume there's only one module with the same module
                # nsvca in pulp.
                module_pulp_href = module_pulp_hrefs[0]['pulp_href']

                packages_to_repo_layout[repo_name][repo_arch].append(
                    module_pulp_href
                )
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
                    models.Repository.arch == arch,
                )
                repo_result = await self.db.execute(repo_q)
                repo: models.Repository = repo_result.scalars().first()
                if not repo:
                    raise MissingRepository(
                        f"Repository with name {repository_name} is missing "
                        "or doesn't have pulp_href field"
                    )
                modify_tasks.append(
                    self.pulp_client.modify_repository(
                        repo.pulp_href,
                        add=packages,
                    )
                )
                # after modify repo we need to publish repo content
                publication_tasks.append(
                    self.pulp_client.create_rpm_publication(repo.pulp_href)
                )
        await asyncio.gather(*modify_tasks)
        await asyncio.gather(*publication_tasks)
        return additional_messages

    @class_measure_work_time_async("check_released_errata_packages")
    async def check_released_errata_packages(
        self,
        release: models.Release,
    ):
        if release.status != ReleaseStatus.COMPLETED:
            return
        package_hrefs = [
            package["package"]["artifact_href"]
            for package in release.plan["packages"]
        ]
        subquery = (
            select(models.BuildTaskArtifact.id)
            .where(models.BuildTaskArtifact.href.in_(package_hrefs))
            .scalar_subquery()
        )
        albs_pkgs = await self.db.execute(
            select(models.NewErrataToALBSPackage)
            .where(
                or_(
                    models.NewErrataToALBSPackage.albs_artifact_id.in_(
                        subquery
                    ),
                    models.NewErrataToALBSPackage.pulp_href.in_(package_hrefs),
                )
            )
            .options(selectinload(models.NewErrataToALBSPackage.errata_package))
        )
        albs_pkgs = albs_pkgs.scalars().all()

        if not albs_pkgs:
            return

        # We assume that a release involves only one errata.
        # If it is not the case, we need to check the errata record status
        # of every errata_to_albs_packages and taking them into account when
        # iterating them below.
        any_errata_package = albs_pkgs[0].errata_package
        errata_record_status = (
            await self.db.execute(
                select(models.NewErrataRecord.release_status).where(
                    models.NewErrataRecord.id
                    == any_errata_package.errata_record_id,
                    models.NewErrataRecord.platform_id
                    == any_errata_package.platform_id,
                )
            )
        ).scalar()

        # Only set their status to 'released' if errata_record is not released
        if errata_record_status != ErrataReleaseStatus.RELEASED:
            for albs_pkg in albs_pkgs:
                albs_pkg.status = ErrataPackageStatus.released
            await self.db.flush()

    @class_measure_work_time_async("update_release_plan")
    async def update_release_plan(
        self,
        plan: dict,
        release: models.Release,
    ) -> dict:
        updated_plan = plan.copy()
        self.base_platform = release.platform
        (
            pkgs_from_repos,
            pkgs_in_repos,
        ) = await self.check_packages_presence_in_prod_repositories(
            plan["packages"],
        )
        updated_plan["packages_from_repos"] = pkgs_from_repos
        updated_plan["packages_in_repos"] = pkgs_in_repos
        return updated_plan

    @class_measure_work_time_async("commit_release")
    async def commit_release(
        self,
        release_id: int,
        user_id: int,
    ) -> typing.Tuple[models.Release, str]:
        release, message = await super().commit_release(release_id, user_id)
        await self.check_released_errata_packages(release)
        return release, message


def get_releaser_class(
    product: models.Product,
) -> typing.Union[
    typing.Type[CommunityReleasePlanner], typing.Type[AlmaLinuxReleasePlanner]
]:
    if product.is_community:
        return CommunityReleasePlanner
    return AlmaLinuxReleasePlanner

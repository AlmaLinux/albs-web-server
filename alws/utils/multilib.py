import asyncio
import logging
import re
import typing

import jmespath
import sqlalchemy
from sqlalchemy import select
from sqlalchemy.orm import Session

from alws import models
from alws.config import settings
from alws.constants import BuildTaskStatus
from alws.dependencies import get_db
from alws.errors import ModuleUpdateError
from alws.utils.beholder_client import BeholderClient
from alws.utils.debuginfo import is_debuginfo_rpm
from alws.utils.parsing import get_clean_distr_name
from alws.utils.pulp_client import PulpClient


__all__ = [
    'add_multilib_packages',
    'get_multilib_packages',
]

from alws.utils.rpm_package import get_rpm_package_info


async def get_build_task_artifacts(db: Session, build_task: models.BuildTask):
    subquery = select(models.BuildTask.id).where(sqlalchemy.and_(
        models.BuildTask.build_id == build_task.build_id,
        models.BuildTask.index == build_task.index,
        models.BuildTask.arch == 'i686',
    )).scalar_subquery()
    query = select(models.BuildTaskArtifact).where(sqlalchemy.and_(
        models.BuildTaskArtifact.build_task_id == subquery,
        models.BuildTaskArtifact.type == 'rpm',
        models.BuildTaskArtifact.name.not_like('%src.rpm%'),
    ))
    db_artifacts = await db.execute(query)
    db_artifacts = list(db_artifacts.scalars().all())
    return db_artifacts


class MultilibProcessor:
    def __init__(self, build_task: models.BuildTask,
                 pulp_client: PulpClient = None, module_index=None):
        self._build_task = build_task
        self._pulp_client = pulp_client
        if not pulp_client:
            self._pulp_client = PulpClient(
                settings.pulp_host, settings.pulp_user,
                settings.pulp_password
            )
        self._module_index = module_index
        self._beholder_client = BeholderClient(
            settings.beholder_host, token=settings.beholder_token
        )
        self._is_multilib_needed = None

    async def __call_beholder(self, endpoint):
        response = {}
        params = {'match': 'closest'}
        try:
            response = await self._beholder_client.get(endpoint, params=params)
        except Exception:
            logging.error(
                "Cannot get multilib packages, trying next reference platform",
            )
        return response

    async def is_multilib_needed(self):
        if self._is_multilib_needed is not None:
            return self._is_multilib_needed

        query = select(models.BuildTask.arch).where(sqlalchemy.and_(
                models.BuildTask.build_id == self._build_task.build_id,
                models.BuildTask.index == self._build_task.index,
                models.BuildTask.status == BuildTaskStatus.COMPLETED,
        ))
        result = True
        async for db in get_db():
            db_build_tasks = await db.execute(query)
            task_arches = list(db_build_tasks.scalars().all())
            if 'i686' not in task_arches:
                result = False
            self._is_multilib_needed = result
        return result

    @staticmethod
    async def parse_response(
            query: str, beholder_response: dict) -> typing.List[dict]:
        result = jmespath.search(query, beholder_response)
        result = jmespath.search(
             "[*].{name: name, version: version, "
             "is_multilib: repos[?arch=='x86_64'].arch[] | "
             "contains(@, 'x86_64')}",
             result,
         )
        return result if result else []

    async def call_for_packages(
            self, platform, src_rpm: str) -> typing.List[dict]:
        ref_name = get_clean_distr_name(platform.name)
        ref_ver = platform.distr_version
        endpoint = f'api/v1/distros/{ref_name}/{ref_ver}/project/{src_rpm}'
        response = await self.__call_beholder(endpoint)
        query = (
            "packages[?arch=='i686']"
            ".{name: name, version: version, repos: repositories}"
        )
        return await self.parse_response(query, response)

    async def call_for_module_artifacts(self, platform) -> typing.List[dict]:
        if not self._module_index:
            return []

        ref_name = get_clean_distr_name(platform.name)
        ref_ver = platform.distr_version
        module_name = self._build_task.rpm_module.name
        module_stream = self._build_task.rpm_module.stream
        endpoint = (f'api/v1/distros/{ref_name}/{ref_ver}/module/'
                    f'{module_name}/{module_stream}/x86_64/')
        response = await self.__call_beholder(endpoint)
        query = (
            "artifacts[*].packages[?arch=='i686']"
            ".{name: name, version: version, repos: repositories}[]"
        )
        packages = await self.parse_response(query, response)
        if self._module_index and self._module_index.has_devel_module():
            module_name = f'{module_name}-devel'
            endpoint = (f'api/v1/distros/{ref_name}/{ref_ver}/module/'
                        f'{module_name}/{module_stream}/x86_64/')
            response = await self.__call_beholder(endpoint)
            devel_packages = await self.parse_response(query, response)
            packages += devel_packages
            # Deduplicate packages
            packages_mapping = {f'{i["name"]}-{i["version"]}': i
                                for i in packages}
            packages = list(packages_mapping.values())
        logging.info('Found something: %s', str(packages))
        return packages

    async def get_packages(self, src_rpm: str):
        packages = None
        platforms = (self._build_task.platform.reference_platforms +
                     [self._build_task.platform])
        for ref_platform in platforms:
            packages = await self.call_for_packages(ref_platform, src_rpm)
            if packages:
                break
        if not packages:
            return {}
        return {
            pkg['name']: pkg['version']
            for pkg in packages
            if pkg['is_multilib'] is True
        }

    async def get_module_artifacts(self):
        if not self._module_index:
            return []
        artifacts = None
        platforms = (self._build_task.platform.reference_platforms +
                     [self._build_task.platform])
        for ref_platform in platforms:
            artifacts = await self.call_for_module_artifacts(ref_platform)
            if artifacts:
                break
        if not artifacts:
            return []
        return [i for i in artifacts if i.get('is_multilib')]

    async def add_multilib_packages(self, multilib_packages: dict):
        proceed = await self.is_multilib_needed()
        if not proceed:
            return

        artifacts = []
        pkg_hrefs = []
        debug_pkg_hrefs = []
        async for db in get_db():
            db_artifacts = await get_build_task_artifacts(db, self._build_task)
            for artifact in db_artifacts:
                href = artifact.href
                rpm_pkg = await self._pulp_client.get_rpm_package(
                    package_href=href,
                    include_fields=['name', 'version'],
                )
                artifact_name = rpm_pkg.get('name', '')
                for pkg_name, pkg_version in multilib_packages.items():
                    add_conditions = (
                        artifact_name == pkg_name,
                        href not in pkg_hrefs or href not in debug_pkg_hrefs,
                    )
                    if all(add_conditions):
                        artifacts.append(models.BuildTaskArtifact(
                            build_task_id=self._build_task.id,
                            name=artifact.name,
                            type=artifact.type,
                            href=href,
                        ))
                        if is_debuginfo_rpm(artifact_name):
                            debug_pkg_hrefs.append(href)
                        else:
                            pkg_hrefs.append(href)
            db.add_all(artifacts)
            await db.commit()
        debug_repo = next(
            r for r in self._build_task.build.repos if r.type == 'rpm'
            and r.arch == 'x86_64' and r.debug is True
        )
        arch_repo = next(
            r for r in self._build_task.build.repos if r.type == 'rpm'
            and r.arch == 'x86_64' and r.debug is False
        )
        await asyncio.gather(
            self._pulp_client.modify_repository(
                repo_to=debug_repo.pulp_href, add=debug_pkg_hrefs),
            self._pulp_client.modify_repository(
                repo_to=arch_repo.pulp_href, add=pkg_hrefs)
        )

    async def update_module_index(self, rpm_packages: list):
        results = await asyncio.gather(
            *(get_rpm_package_info(
                self._pulp_client, rpm.href,
                include_fields=['epoch', 'name', 'version', 'release', 'arch']
            ) for rpm in rpm_packages)
        )

        packages_info = dict(results)
        # If module has devel sibling and it's not Python then multilib
        # goes into devel module
        module_name = self._build_task.rpm_module.name
        module_stream = self._build_task.rpm_module.stream
        devel = False
        if self._module_index.has_devel_module() \
                and 'python' not in module_name:
            module = self._module_index.get_module(
                f'{module_name}-devel', module_stream)
            devel = True
        else:
            module = self._module_index.get_module(module_name, module_stream)
        try:
            for rpm in rpm_packages:
                rpm_package = packages_info[rpm.href]
                module.add_rpm_artifact(rpm_package, devel=devel)
        except Exception as e:
            raise ModuleUpdateError('Cannot update module: %s', str(e)) from e

    async def add_multilib_module_artifacts(
            self, prepared_artifacts: list = None):
        if not self._module_index:
            return

        artifacts = prepared_artifacts or (await self.get_module_artifacts())
        if not artifacts:
            return
        packages_to_process = {}
        async for db in get_db():
            db_artifacts = await get_build_task_artifacts(db, self._build_task)
            for artifact in artifacts:
                if not artifact['is_multilib']:
                    continue
                for package in db_artifacts:
                    if artifact['name'] in package.name:
                        packages_to_process[artifact['name']] = package

        await self.update_module_index(list(packages_to_process.values()))


async def get_multilib_packages(
        db: Session,
        build_task: models.BuildTask,
        src_rpm: str,
) -> dict:

    async def call_beholder(endpoint: str) -> dict:
        response = {}
        try:
            response = await beholder_client.get(endpoint)
        except Exception:
            logging.error(
                "Cannot get multilib packages, trying next reference platform",
            )
        return response

    async def parse_beholder_response(beholder_response: dict) -> dict:
        multilib_dict = jmespath.search(
            "packages[?arch=='i686'].{name: name, version: version, "
            "repos: repositories}",
            beholder_response,
        )
        multilib_dict = jmespath.search(
            "[*].{name: name, version: version, "
            "is_multilib: repos[?arch=='x86_64'].arch[] | "
            "contains(@, 'x86_64')}",
            multilib_dict,
        )
        return multilib_dict if multilib_dict is not None else {}

    query = select(models.BuildTask).where(sqlalchemy.and_(
        models.BuildTask.build_id == build_task.build_id,
        models.BuildTask.index == build_task.index,
        models.BuildTask.status == BuildTaskStatus.COMPLETED,
    ))
    db_build_tasks = await db.execute(query)
    task_arches = [task.arch for task in db_build_tasks.scalars().all()]
    result = {}
    multilib_packages = {}
    if 'i686' not in task_arches:
        return result

    beholder_client = BeholderClient(
        host=settings.beholder_host,
        token=settings.beholder_token,
    )

    for ref_platform in build_task.platform.reference_platforms:
        ref_name = ref_platform.name[:-1]
        ref_ver = ref_platform.distr_version
        endpoint = f'api/v1/distros/{ref_name}/{ref_ver}/project/{src_rpm}'
        pkg_info = await call_beholder(endpoint)
        multilib_packages = await parse_beholder_response(pkg_info)
        if multilib_packages:
            break

    if not multilib_packages:
        distr_name = build_task.platform.data['definitions']['distribution']
        distr_ver = build_task.platform.distr_version
        endpoint = f'api/v1/distros/{distr_name}/{distr_ver}/project/{src_rpm}'
        pkg_info = await call_beholder(endpoint)
        multilib_packages = await parse_beholder_response(pkg_info)

    result = {
        pkg['name']: pkg['version']
        for pkg in multilib_packages
        if pkg['is_multilib'] is True
    }
    return result


async def add_multilib_packages(
        db: Session,
        pulp_client: PulpClient,
        build_task: models.BuildTask,
        multilib_packages: dict,
):
    subquery = select(models.BuildTask.id).where(sqlalchemy.and_(
        models.BuildTask.build_id == build_task.build_id,
        models.BuildTask.index == build_task.index,
        models.BuildTask.arch == 'i686',
    )).scalar_subquery()
    query = select(models.BuildTaskArtifact).where(sqlalchemy.and_(
        models.BuildTaskArtifact.build_task_id == subquery,
        models.BuildTaskArtifact.type == 'rpm',
        models.BuildTaskArtifact.name.not_like('%src.rpm%'),
    ))
    db_artifacts = await db.execute(query)
    db_artifacts = db_artifacts.scalars().all()

    artifacts = []
    pkg_hrefs = []
    debug_pkg_hrefs = []

    for artifact in db_artifacts:
        href = artifact.href
        rpm_pkg = await pulp_client.get_rpm_package(
            package_href=href,
            include_fields=['name', 'version'],
        )
        artifact_name = rpm_pkg.get('name', '')
        for pkg_name, pkg_version in multilib_packages.items():
            add_conditions = (
               artifact_name == pkg_name,
               rpm_pkg.get('version', '') == pkg_version,
               href not in pkg_hrefs or href not in debug_pkg_hrefs,
            )
            if all(add_conditions):
                artifacts.append(models.BuildTaskArtifact(
                    build_task_id=build_task.id,
                    name=artifact.name,
                    type=artifact.type,
                    href=href,
                ))
                if re.search(r'-debug(info|source)$', artifact_name):
                    debug_pkg_hrefs.append(href)
                else:
                    pkg_hrefs.append(href)
    db.add_all(artifacts)
    await db.flush()

    debug_repo = next(
        r for r in build_task.build.repos if r.type == 'rpm'
        and r.arch == 'x86_64' and r.debug is True
    )
    arch_repo = next(
        r for r in build_task.build.repos if r.type == 'rpm'
        and r.arch == 'x86_64' and r.debug is False
    )
    await asyncio.gather(
        pulp_client.modify_repository(
            repo_to=debug_repo.pulp_href, add=debug_pkg_hrefs),
        pulp_client.modify_repository(
            repo_to=arch_repo.pulp_href, add=pkg_hrefs)
    )

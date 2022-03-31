import asyncio
import logging
import re

import jmespath
import sqlalchemy
from sqlalchemy import select
from sqlalchemy.orm import Session

from alws import models
from alws.config import settings
from alws.constants import BuildTaskStatus
from alws.utils.beholder_client import BeholderClient
from alws.utils.parsing import get_clean_distr_name
from alws.utils.pulp_client import PulpClient


__all__ = [
    'add_multilib_packages',
    'get_multilib_packages',
]


async def get_multilib_packages(
        db: Session,
        build_task: models.BuildTask,
        src_rpm: str,
) -> (dict, list):

    async def call_beholder(endpoint: str, is_module: bool = False) -> dict:
        response = {}
        params = {}
        if is_module:
            params['match'] = 'closest'
        try:
            response = await beholder_client.get(endpoint, params=params)
        except Exception:
            logging.error(
                "Cannot get multilib packages, trying next reference platform",
            )
        return response

    async def parse_beholder_response(
        beholder_response: dict,
        is_module: bool = False,
    ) -> list:
        jmespath_query = (
            "packages[?arch=='i686']"
            ".{name: name, version: version, repos: repositories}"
        )
        if is_module:
            jmespath_query = (
                "artifacts[*].packages[?arch=='i686']"
                ".{name: name, version: version, repos: repositories}[]"
            )
        multilib_list = jmespath.search(jmespath_query,
                                        beholder_response)
        multilib_list = jmespath.search(
            "[*].{name: name, version: version, "
            "is_multilib: repos[?arch=='x86_64'].arch[] | "
            "contains(@, 'x86_64')}",
            multilib_list,
        )
        return multilib_list if multilib_list is not None else []

    query = select(models.BuildTask).where(sqlalchemy.and_(
        models.BuildTask.build_id == build_task.build_id,
        models.BuildTask.index == build_task.index,
        models.BuildTask.status == BuildTaskStatus.COMPLETED,
    ))
    db_build_tasks = await db.execute(query)
    task_arches = [task.arch for task in db_build_tasks.scalars().all()]
    result = {}
    beholder_response = {}
    multilib_packages = []
    module_artifacts = []
    if 'i686' not in task_arches:
        return result

    beholder_client = BeholderClient(
        host=settings.beholder_host,
        token=settings.beholder_token,
    )
    is_module = False
    module_name, module_stream = None, None
    if build_task.rpm_module_id:
        is_module = True
        rpm_module = await db.execute(
            select(models.RpmModule).where(
                models.RpmModule.id == build_task.rpm_module_id)
        )
        rpm_module = rpm_module.scalars().first()
        module_name = rpm_module.name
        module_stream = rpm_module.stream

    for ref_platform in build_task.platform.reference_platforms:
        ref_name = get_clean_distr_name(ref_platform.name)
        ref_ver = ref_platform.distr_version
        endpoint = f'api/v1/distros/{ref_name}/{ref_ver}/project/{src_rpm}'
        if is_module:
            endpoint = (f'api/v1/distros/{ref_name}/{ref_ver}/module/'
                        f'{module_name}/{module_stream}/x86_64/')
        beholder_response = await call_beholder(endpoint, is_module=is_module)
        multilib_packages = await parse_beholder_response(beholder_response,
                                                          is_module)
        if multilib_packages:
            break

    if not multilib_packages:
        distr_name = get_clean_distr_name(build_task.platform.name)
        distr_ver = build_task.platform.distr_version
        endpoint = f'api/v1/distros/{distr_name}/{distr_ver}/project/{src_rpm}'
        if is_module:
            endpoint = (f'api/v1/distros/{distr_name}/{distr_ver}/module/'
                        f'{module_name}/{module_stream}/x86_64/')
        beholder_response = await call_beholder(endpoint, is_module=is_module)
        multilib_packages = await parse_beholder_response(beholder_response,
                                                          is_module)

    result = {
        pkg['name']: pkg['version']
        for pkg in multilib_packages
        if pkg['is_multilib'] is True
    }
    if is_module and multilib_packages:
        for artifact_dict in beholder_response.get('artifacts', []):
            for package in artifact_dict.get('packages', []):
                if package['name'] in result:
                    module_artifacts.append(package)
    return result, module_artifacts


async def add_multilib_packages(
        db: Session,
        build_task: models.BuildTask,
        multilib_packages: dict,
        # TODO: Need to add logic for updating module template 
        # after placing multilib packages in pulp repos
        module_artifacts: list,
):
    pulp_client = PulpClient(
        settings.pulp_host,
        settings.pulp_user,
        settings.pulp_password,
    )
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
    await db.commit()

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

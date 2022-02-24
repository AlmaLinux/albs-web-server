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
from alws.utils.pulp_client import PulpClient


__all__ = [
    'add_multilib_packages',
    'get_multilib_packages',
]


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
        build_task: models.BuildTask,
        multilib_packages: dict,
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

    for repo in build_task.build.repos:
        if repo.arch != 'x86_64' and repo.type != 'rpm':
            continue
        hrefs_to_add = debug_pkg_hrefs if repo.debug else pkg_hrefs
        await pulp_client.modify_repository(
            repo_to=repo.pulp_href, add=hrefs_to_add)

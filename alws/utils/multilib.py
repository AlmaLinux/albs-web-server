import logging

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
    query = select(models.BuildTask).where(sqlalchemy.and_(
        models.BuildTask.build_id == build_task.build_id,
        models.BuildTask.index == build_task.index,
        models.BuildTask.status == BuildTaskStatus.COMPLETED,
    ))
    db_build_tasks = await db.execute(query)
    task_arches = [task.arch for task in db_build_tasks.scalars().all()]
    result = {}
    if 'i686' not in task_arches:
        return result

    distr_name = build_task.platform.data['definitions']['distribution']
    distr_ver = build_task.platform.distr_version
    endpoint = f'api/v1/distros/{distr_name}/{distr_ver}/project/{src_rpm}'

    beholder_client = BeholderClient(
        host=settings.beholder_host,
        token=settings.beholder_token,
    )
    try:
        pkg_info = await beholder_client.get(endpoint)
    except Exception as exc:
        logging.exception("Cannot get multilib packages: %s", exc)
        return result
    multilib_packages = jmespath.search(
        "packages[?arch=='i686'].{name: name, version: version, "
        "repos: repositories}",
        pkg_info,
    )
    multilib_packages = jmespath.search(
        "[*].{name: name, version: version, "
        "is_multilib: repos[?arch=='x86_64'].arch[] | contains(@, 'x86_64')}",
        multilib_packages,
    )
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
    async with db.begin():
        subquery = select(models.BuildTask.id).where(sqlalchemy.and_(
            models.BuildTask.build_id == build_task.build_id,
            models.BuildTask.index == build_task.index,
            models.BuildTask.arch == 'i686',
        )).scalar_subquery()
        query = select(models.BuildTaskArtifact).where(sqlalchemy.and_(
            models.BuildTaskArtifact.build_task_id == subquery,
            models.BuildTaskArtifact.type == 'rpm',
            models.BuildTaskArtifact.name.not_like('%-debuginfo-%'),
            models.BuildTaskArtifact.name.not_like('%-debugsource-%'),
            models.BuildTaskArtifact.name.not_like('%src.rpm%'),
        ))
        db_artifacts = await db.execute(query)
        db_artifacts = db_artifacts.scalars().all()

        modify_repo_href = next(
            repo.pulp_href for repo in build_task.build.repos
            if repo.arch == 'x86_64'
            and repo.type == 'rpm'
            and repo.debug is False
        )
        artifacts = []
        pkg_hrefs = []

        for artifact in db_artifacts:
            for pkg_name, pkg_version in multilib_packages.items():
                if artifact.name.startswith(pkg_name):
                    rpm_pkg = await pulp_client.get_rpm_package(
                        package_href=artifact.href,
                        include_fields=['name', 'version'],
                    )
                    if rpm_pkg and rpm_pkg['version'] == pkg_version:
                        artifacts.append(
                            models.BuildTaskArtifact(
                                build_task_id=build_task.id,
                                name=artifact.name,
                                type=artifact.type,
                                href=artifact.href,
                            )
                        )
                        pkg_hrefs.append(artifact.href)
        db.add_all(artifacts)
        await db.commit()

    await pulp_client.modify_repository(
        repo_to=modify_repo_href, add=pkg_hrefs)

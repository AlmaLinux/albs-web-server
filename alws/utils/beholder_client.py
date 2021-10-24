import urllib.parse

import aiohttp
import jmespath
import sqlalchemy
from sqlalchemy import select
from sqlalchemy.orm import Session

from alws import models
from alws.config import settings
from alws.constants import BuildTaskStatus
from alws.utils.pulp_client import PulpClient


__all__ = [
    'add_multilib_packages',
    'is_multilib_package',
]


class BeholderClient:
    def __init__(self):
        self._host = settings.beholder_host
        self._headers = {}
        if settings.beholder_token:
            self._headers.update({
                'Authorization': f'Bearer {settings.beholder_token}',
            })

    def _get_url(self, endpoint: str) -> str:
        return urllib.parse.urljoin(self._host, endpoint)

    async def get(self, endpoint: str,
                  headers: dict = None, params: dict = None):
        req_headers = self._headers.copy()
        if headers:
            req_headers.update(**headers)
        full_url = self._get_url(endpoint)
        async with aiohttp.ClientSession(headers=req_headers) as session:
            async with session.get(full_url, params=params) as response:
                json = await response.json()
                response.raise_for_status()
                return json


async def is_multilib_package(
        db: Session,
        build_task: models.BuildTask,
        src_rpm,
) -> bool:
    query = select(models.BuildTask).where(sqlalchemy.and_(
        models.BuildTask.build_id == build_task.build_id,
        models.BuildTask.index == build_task.index,
        models.BuildTask.status == BuildTaskStatus.COMPLETED,
    ))
    db_build_tasks = await db.execute(query)
    task_archs = [task.arch for task in db_build_tasks.scalars().all()]
    if 'i686' not in task_archs:
        return False

    endpoint = 'api/v1/distros/{distr}/{distr_ver}/project/{src_rpm}'.format(
        distr=build_task.platform.data['definitions']['distribution'],
        distr_ver=build_task.platform.distr_version,
        src_rpm=src_rpm,
    )
    pkg_info = await BeholderClient().get(endpoint)
    result = jmespath.search("packages[?arch=='i686'].repositories", pkg_info)
    result = jmespath.search(
        "[*][?arch=='x86_64'].arch[] | contains(@, 'x86_64')",
        result,
    )
    return result


async def add_multilib_packages(db: Session, build_task: models.BuildTask):
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

    pulp_client = PulpClient(
        settings.pulp_host,
        settings.pulp_user,
        settings.pulp_password
    )
    await pulp_client.modify_repository(
        repo_to=modify_repo_href, add=pkg_hrefs)

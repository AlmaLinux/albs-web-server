import copy
import typing

import sqlalchemy
from sqlalchemy.future import select
from sqlalchemy.orm import Session, selectinload

from alws import models
from alws.config import settings
from alws.constants import BuildTaskStatus
from alws.utils.pulp_client import PulpClient


__all__ = [
    'get_noarch_packages',
    'save_noarch_packages',
]


async def get_noarch_packages(
    db: Session,
    build_task_ids: typing.List[int]
) -> typing.Tuple[dict, dict]:
    query = select(models.BuildTaskArtifact).where(sqlalchemy.and_(
        models.BuildTaskArtifact.build_task_id.in_(build_task_ids),
        models.BuildTaskArtifact.type == 'rpm',
        models.BuildTaskArtifact.name.like('%.noarch.%'),
    ))
    db_artifacts = await db.execute(query)
    db_artifacts = db_artifacts.scalars().all()
    noarch_packages = {}
    debug_noarch_packages = {}
    for artifact in db_artifacts:
        if '-debuginfo-' in artifact.name or '-debugsource-' in artifact.name:
            debug_noarch_packages[artifact.name] = artifact.href
            continue
        noarch_packages[artifact.name] = artifact.href

    return noarch_packages, debug_noarch_packages


async def save_noarch_packages(db: Session, build_task: models.BuildTask):
    query = select(models.BuildTask).where(sqlalchemy.and_(
        models.BuildTask.build_id == build_task.build_id,
        models.BuildTask.index == build_task.index,
    )).options(
        selectinload(models.BuildTask.artifacts),
        selectinload(models.BuildTask.build).selectinload(models.Build.repos),
    )
    pulp_client = PulpClient(
        settings.pulp_host,
        settings.pulp_user,
        settings.pulp_password,
    )
    build_tasks = await db.execute(query)
    build_tasks = build_tasks.scalars().all()
    if not all(
            BuildTaskStatus.is_finished(task.status)
            for task in build_tasks):
        return

    build_task_ids = [task.id for task in build_tasks]
    noarch_packages, debug_noarch_packages = await get_noarch_packages(
        db, build_task_ids)
    if not any((noarch_packages, debug_noarch_packages)):
        return

    repos_to_update = {}
    new_noarch_artifacts = []
    hrefs_to_add = list(noarch_packages.values())
    debug_hrefs_to_add = list(debug_noarch_packages.values())

    for task in build_tasks:
        if task.status in (BuildTaskStatus.FAILED,
                           BuildTaskStatus.EXCLUDED):
            continue
        noarch = copy.deepcopy(noarch_packages)
        debug_noarch = copy.deepcopy(debug_noarch_packages)
        hrefs_to_delete = []
        debug_hrefs_to_delete = []

        # replace hrefs for existing artifacts in database
        # and create new artifacts if they doesn't exist
        for artifact in task.artifacts:
            if artifact.name in noarch:
                hrefs_to_delete.append(artifact.href)
                artifact.href = noarch.pop(artifact.name)
            if artifact.name in debug_noarch:
                debug_hrefs_to_delete.append(artifact.href)
                artifact.href = debug_noarch.pop(artifact.name)

        artifacts_to_create = {**noarch, **debug_noarch}
        for name, href in artifacts_to_create.items():
            new_noarch_artifacts.append(
                models.BuildTaskArtifact(
                    build_task_id=task.id,
                    name=name,
                    type='rpm',
                    href=href,
                )
            )

        for repo in build_task.build.repos:
            if (repo.arch == 'src' or repo.type != 'rpm'
                    or repo.arch != task.arch):
                continue
            repo_href = repo.pulp_href
            add_content = hrefs_to_add
            remove_content = hrefs_to_delete
            if repo.debug:
                add_content = debug_hrefs_to_add
                remove_content = debug_hrefs_to_delete
            repos_to_update[repo_href] = {
                'add': add_content,
                'remove': remove_content,
            }

    db.add_all(build_tasks)
    db.add_all(new_noarch_artifacts)
    await db.flush()

    for repo_href, content_dict in repos_to_update.items():
        await pulp_client.modify_repository(
            repo_to=repo_href,
            add=content_dict['add'],
            remove=content_dict['remove'],
        )

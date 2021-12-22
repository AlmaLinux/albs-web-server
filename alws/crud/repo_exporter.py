import datetime
import logging
import typing
from pathlib import Path

import sqlalchemy
from sqlalchemy import update, delete, insert
from sqlalchemy.future import select
from sqlalchemy.orm import Session

from alws import models
from alws.errors import (
    AlreadyBuiltError,
    DataNotFoundError,
    DistributionError,
)
from alws.config import settings

from alws.schemas import (
    build_schema, user_schema, platform_schema, build_node_schema,
    distro_schema, test_schema, release_schema, remote_schema,
    repository_schema,
)
from alws.utils.distro_utils import create_empty_repo
from alws.utils.modularity import ModuleWrapper
from alws.utils.github import get_user_github_token, get_github_user_info
from alws.utils.jwt_utils import generate_JWT_token
from alws.utils.multilib import (
    add_multilib_packages,
    get_multilib_packages,
)
from alws.utils.noarch import save_noarch_packages
from alws.utils.pulp_client import PulpClient
from alws.utils.repository import generate_repository_path


async def create_pulp_exporters_to_fs(db: Session,
                                      repo_list: typing.List[int]):
    query = select(models.Repository).where(
        models.Repository.id.in_(repo_list))
    export_name = ','.join((str(r) for r in repo_list))
    export_repos = []
    pulp_client = PulpClient(settings.pulp_host, settings.pulp_user,
                             settings.pulp_password)
    async with db.begin():
        et_inserted = await db.execute(
            insert(models.ExportTask).values(
                name=export_name, status=0)
        )
        export_task_pk = et_inserted.inserted_primary_key[0]
        response = await db.execute(query)
        await db.commit()
    for repo in response.scalars().all():
        export_path = str(Path(settings.pulp_export_path,
                               generate_repository_path(
                                   export_task_pk, repo.name,
                                   repo.arch, repo.debug)))
        fs_exporter_href = await pulp_client.create_filesystem_exporter(
            repo.name, export_path)
        export_repos.append({
            'path': export_path,
            'exported_id': export_task_pk,
            'repository_id': repo.id,
            'fs_exporter_href': fs_exporter_href
        })
    if export_repos:
        async with db.begin():
            await db.execute(
                insert(models.RepoExporter), export_repos)
            await db.commit()
    return export_task_pk


async def execute_pulp_exporters_to_fs(db: Session,
                                       export_id: int):
    pulp_client = PulpClient(settings.pulp_host, settings.pulp_user,
                             settings.pulp_password)
    now = datetime.datetime.now()
    query = select(
        models.RepoExporter.fs_exporter_href,
        models.RepoExporter.path,
        models.Repository.pulp_href
    ).where(
        models.RepoExporter.exported_id == export_id
    ).join(
        models.Repository
    ).filter(
        models.RepoExporter.repository_id == models.Repository.id)
    async with db.begin():
        await db.execute(
            update(models.ExportTask).where(
                models.ExportTask.id == export_id).values(exported_at=now,
                                                          status=1))
        response = await db.execute(query)
        await db.commit()
    exported_paths = []
    for fs_exporter_href, fse_path, pulp_href in response:
        latest_version_href = await pulp_client.get_repo_latest_version(
            pulp_href)
        await pulp_client.export_to_filesystem(
            fs_exporter_href, latest_version_href)
        exported_paths.append(fse_path)
        await pulp_client.delete_filesystem_exporter(fs_exporter_href)
    async with db.begin():
        await db.execute(
            update(models.ExportTask).where(
                models.ExportTask.id == export_id).values(exported_at=now,
                                                          status=3))
        await db.commit()
    return exported_paths


async def create_filesystem_exporter(name : str, path: str) -> str:
    pulp_client = PulpClient(settings.pulp_host, settings.pulp_user,
                             settings.pulp_password)
    result = await pulp_client.create_filesystem_exporter(name, path)
    return result

async def list_filesystem_exporters() -> list:
    pulp_client = PulpClient(settings.pulp_host, settings.pulp_user,
                             settings.pulp_password)
    result = await pulp_client.list_filesystem_exporters()
    return result

async def get_filesystem_exporter(fse_pulp_href: str):
    pulp_client = PulpClient(settings.pulp_host, settings.pulp_user,
                             settings.pulp_password)
    result = await pulp_client.get_filesystem_exporter(fse_pulp_href)
    return result

async def update_filesystem_exporter(fse_pulp_href: str,
                                     fse_name: str,
                                     fse_path : str):
    pulp_client = PulpClient(settings.pulp_host, settings.pulp_user,
                             settings.pulp_password)
    result = await pulp_client.update_filesystem_exporter(
        fse_pulp_href, fse_name, fse_path)
    return result

async def delete_filesystem_exporter(fse_pulp_href: str):
    pulp_client = PulpClient(settings.pulp_host, settings.pulp_user,
                             settings.pulp_password)
    result = await pulp_client.delete_filesystem_exporter(
        fse_pulp_href)
    return result

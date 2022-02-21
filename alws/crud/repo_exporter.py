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
from alws.constants import ExportStatus

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
    et_inserted = db.execute(
        insert(models.ExportTask).values(
            name=export_name, status=ExportStatus.NEW)
    )
    export_task_pk = et_inserted.inserted_primary_key[0]
    response = db.execute(query)
    db.flush()
    for repo in response.scalars().all():
        export_path = str(Path(settings.pulp_export_path,
                               generate_repository_path(
                                   repo.name, repo.arch, repo.debug)))
        fs_exporter_href = await pulp_client.create_filesystem_exporter(
            repo.name, export_path)
        export_repos.append({
            'path': export_path,
            'exported_id': export_task_pk,
            'repository_id': repo.id,
            'fs_exporter_href': fs_exporter_href
        })
    if export_repos:
        db.execute(
            insert(models.RepoExporter), export_repos)
        db.flush()
    return export_task_pk


async def execute_pulp_exporters_to_fs(db: Session,
                                       export_id: int):
    pulp_client = PulpClient(settings.pulp_host, settings.pulp_user,
                             settings.pulp_password)
    now = datetime.datetime.now()
    query = select(
        models.RepoExporter.fs_exporter_href,
        models.RepoExporter.path,
        models.Repository.pulp_href,
        models.Repository.url
    ).where(
        models.RepoExporter.exported_id == export_id
    ).join(
        models.Repository
    ).filter(
        models.RepoExporter.repository_id == models.Repository.id)
    db.execute(
        update(models.ExportTask).where(
            models.ExportTask.id == export_id).values(
            exported_at=now, status=ExportStatus.IN_PROGRESS))
    response = db.execute(query)
    db.flush()
    exported_data = {}
    for fs_exporter_href, fse_path, pulp_href, repo_url in response:
        latest_version_href = await pulp_client.get_repo_latest_version(
            pulp_href)
        await pulp_client.export_to_filesystem(
            fs_exporter_href, latest_version_href)
        exported_data[fse_path] = repo_url
        await pulp_client.delete_filesystem_exporter(fs_exporter_href)
    db.execute(
        update(models.ExportTask).where(
            models.ExportTask.id == export_id).values(
            exported_at=now, status=ExportStatus.COMPLETED))
    db.flush()
    return exported_data


async def create_filesystem_exporter(name: str, path: str) -> str:
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
                                     fse_path: str):
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

import datetime
import typing
from pathlib import Path

from sqlalchemy import delete, insert, update
from sqlalchemy.future import select
from sqlalchemy.orm import Session

from alws import models
from alws.config import settings
from alws.constants import ExportStatus
from alws.utils.pulp_client import PulpClient


async def create_pulp_exporters_to_fs(db: Session, repo_list: typing.List[int]):
    query = select(models.Repository).where(models.Repository.id.in_(repo_list))
    export_name = ','.join((str(r) for r in repo_list))
    export_repos = []
    pulp_client = PulpClient(
        settings.pulp_host, settings.pulp_user, settings.pulp_password
    )
    et_inserted = await db.execute(
        insert(models.ExportTask).values(
            name=export_name, status=ExportStatus.NEW
        )
    )
    export_task_pk = et_inserted.inserted_primary_key[0]
    response = await db.execute(query)
    await db.flush()
    for repo in response.scalars().all():
        export_path = str(
            Path(settings.pulp_export_path, repo.export_path, 'Packages')
        )
        fs_exporter_href = await pulp_client.create_filesystem_exporter(
            f'{repo.name}-{repo.arch}', export_path
        )
        export_repos.append({
            'path': export_path,
            'exported_id': export_task_pk,
            'repository_id': repo.id,
            'fs_exporter_href': fs_exporter_href,
        })
    if export_repos:
        await db.execute(insert(models.RepoExporter), export_repos)
        await db.flush()
    return export_task_pk


async def execute_pulp_exporters_to_fs(db: Session, export_id: int):
    pulp_client = PulpClient(
        settings.pulp_host, settings.pulp_user, settings.pulp_password
    )
    now = datetime.datetime.utcnow()
    query = (
        select(
            models.RepoExporter.fs_exporter_href,
            models.RepoExporter.path,
            models.Repository.pulp_href,
            models.Repository.url,
        )
        .where(models.RepoExporter.exported_id == export_id)
        .join(models.Repository)
        .filter(models.RepoExporter.repository_id == models.Repository.id)
    )
    await db.execute(
        update(models.ExportTask)
        .where(models.ExportTask.id == export_id)
        .values(exported_at=now, status=ExportStatus.IN_PROGRESS)
    )
    response = await db.execute(query)
    await db.flush()
    exported_data = {}
    for fs_exporter_href, fse_path, pulp_href, repo_url in response:
        latest_version_href = await pulp_client.get_repo_latest_version(
            pulp_href
        )
        await pulp_client.export_to_filesystem(
            fs_exporter_href, latest_version_href
        )
        exported_data[fse_path] = repo_url
        await pulp_client.delete_filesystem_exporter(fs_exporter_href)
    await db.execute(
        update(models.ExportTask)
        .where(models.ExportTask.id == export_id)
        .values(exported_at=now, status=ExportStatus.COMPLETED)
    )
    await db.execute(
        delete(models.RepoExporter).where(
            models.RepoExporter.exported_id == export_id
        )
    )
    await db.flush()
    return exported_data


async def create_filesystem_exporter(name: str, path: str) -> str:
    pulp_client = PulpClient(
        settings.pulp_host, settings.pulp_user, settings.pulp_password
    )
    result = await pulp_client.create_filesystem_exporter(name, path)
    return result


async def list_filesystem_exporters() -> list:
    pulp_client = PulpClient(
        settings.pulp_host, settings.pulp_user, settings.pulp_password
    )
    result = await pulp_client.list_filesystem_exporters()
    return result


async def get_filesystem_exporter(fse_pulp_href: str):
    pulp_client = PulpClient(
        settings.pulp_host, settings.pulp_user, settings.pulp_password
    )
    result = await pulp_client.get_filesystem_exporter(fse_pulp_href)
    return result


async def update_filesystem_exporter(
    fse_pulp_href: str, fse_name: str, fse_path: str
):
    pulp_client = PulpClient(
        settings.pulp_host, settings.pulp_user, settings.pulp_password
    )
    result = await pulp_client.update_filesystem_exporter(
        fse_pulp_href, fse_name, fse_path
    )
    return result


async def delete_filesystem_exporter(fse_pulp_href: str):
    pulp_client = PulpClient(
        settings.pulp_host, settings.pulp_user, settings.pulp_password
    )
    result = await pulp_client.delete_filesystem_exporter(fse_pulp_href)
    return result

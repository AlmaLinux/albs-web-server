import typing

from fastapi import APIRouter, Depends

from alws.auth import get_current_user
from alws.crud import repo_exporter
from alws.schemas.exporter_schema import FileSystemExporter


router = APIRouter(
    prefix='/exporters',
    tags=['exporters', 'fs_exporters', 'filesystem_exporters'],
    dependencies=[Depends(get_current_user)]
)


@router.post('/', response_model=str)
async def create_fs_exporter(name: str, path: str) -> str:
    pulp_href = await repo_exporter.create_filesystem_exporter(name, path)
    return pulp_href


@router.get('/', response_model=typing.List[FileSystemExporter])
async def list_fs_exporters():
    exporter_list = await repo_exporter.list_filesystem_exporters()
    return exporter_list


@router.get('/{fse_pulp_href}/',
            response_model=typing.List[FileSystemExporter])
async def get_fs_exporter(fse_pulp_href : str):
    exporter_list = await repo_exporter.get_filesystem_exporter(fse_pulp_href)
    return exporter_list


@router.put('/{fse_pulp_href}/',
            response_model=dict)
async def update_fs_exporter(fse_pulp_href : str,
                             fse_name: str,
                             fse_path : str):
    updated_result = await repo_exporter.update_filesystem_exporter(
        fse_pulp_href, fse_name, fse_path)
    return updated_result


@router.delete('/{fse_pulp_href}/',
               response_model=dict)
async def delete_fs_exporter(fse_pulp_href : str):
    deleted_result = await repo_exporter.delete_filesystem_exporter(
        fse_pulp_href)
    return deleted_result

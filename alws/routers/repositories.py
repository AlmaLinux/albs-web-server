import typing

from fastapi import APIRouter, Depends

from alws import database
from alws.crud import repository
from alws.crud import repo_exporter
from alws.dependencies import get_db, JWTBearer
from alws.schemas import repository_schema


router = APIRouter(
    prefix='/repositories',
    tags=['repositories'],
    dependencies=[Depends(JWTBearer())]
)


@router.get('/', response_model=typing.List[repository_schema.Repository])
async def get_repositories(db: database.Session = Depends(get_db)):
    return await repository.get_repositories(db)


@router.get('/{repository_id}/',
            response_model=typing.Union[None, repository_schema.Repository])
async def get_repository(repository_id: int, db: database.Session = Depends(get_db)):
    result = await repository.get_repositories(db, repository_id=repository_id)
    if result:
        return result[0]
    return None


@router.post('/exports/', response_model=typing.List[str])
async def fs_export_repository(repository_ids: list,
                               db: database.Session = Depends(get_db)):
    export_task = await repo_exporter.create_pulp_exporters_to_fs(
        db, repository_ids)
    export_pashs = await repo_exporter.execute_pulp_exporters_to_fs(db, export_task)
    return export_pashs
import typing

from fastapi import APIRouter, Depends

from alws import database
from alws.auth import get_current_user
from alws.crud import repository
from alws.dependencies import get_db
from alws.utils.exporter import fs_export_repository
from alws.schemas import repository_schema


router = APIRouter(
    prefix='/repositories',
    tags=['repositories'],
    dependencies=[Depends(get_current_user)]
)


@router.get('/', response_model=typing.List[repository_schema.Repository])
async def get_repositories(db: database.Session = Depends(get_db)):
    return await repository.get_repositories(db)


@router.get('/{repository_id}/',
            response_model=typing.Union[None, repository_schema.Repository])
async def get_repository(repository_id: int,
                         db: database.Session = Depends(get_db)):
    result = await repository.get_repositories(db, repository_id=repository_id)
    if result:
        return result[0]
    return None


@router.post('/exports/', response_model=typing.List[str])
async def filesystem_export_repository(repository_ids: typing.List[int],
                                       db: database.Session = Depends(get_db)):
    return await fs_export_repository(repository_ids, db)

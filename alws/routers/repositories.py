import typing

from fastapi import APIRouter, Depends

from alws import database
from alws.crud import repository
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


@router.post('/exports/', response_model=typing.List[int])
async def fs_export_repository(repository_ids: list,
                               db: database.Session = Depends(get_db)):
    #res = await crud.create_pulp_exporters_to_fs(db, repository_ids)
    res = 12
    print(666)
    print(res)
    await crud.execute_pulp_exporters_to_fs(db, res)
    print(888)
    return res
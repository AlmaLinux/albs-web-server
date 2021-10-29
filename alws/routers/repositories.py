import typing

from fastapi import APIRouter, Depends

from alws import database, crud
from alws.dependencies import get_db, JWTBearer
from alws.schemas import repository_schema


router = APIRouter(
    prefix='/repositories',
    tags=['repositories'],
    dependencies=[Depends(JWTBearer())]
)


@router.get('/', response_model=typing.List[repository_schema.Repository])
async def get_repositories(db: database.Session = Depends(get_db)):
    return await crud.get_repositories(db)


@router.get('/{repository_id}/',
            response_model=typing.Union[None, repository_schema.Repository])
async def get_repository(repository_id: int, db: database.Session = Depends(get_db)):
    result = await crud.get_repositories(db, repository_id=repository_id)
    if result:
        return result[0]
    return None

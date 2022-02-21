import typing

from fastapi import APIRouter, Depends, FastAPI, HTTPException, status

from alws.dependencies import JWTBearer, get_sync_db
from alws import database
from alws.crud import distribution as distro_crud
from alws.schemas import distro_schema
from alws.errors import DistributionError

app = FastAPI()
router = APIRouter(
    prefix='/distro',
    tags=['distro'],
    dependencies=[Depends(JWTBearer())]
)


@router.post('/', response_model=distro_schema.Distribution)
async def create_distribution(distribution: distro_schema.DistroCreate):
    with get_sync_db() as db:
        return await distro_crud.create_distro(db, distribution)


@router.post('/add/{build_id}/{distribution}/',
             response_model=typing.Dict[str, bool])
async def add_to_distribution(
        distribution: str,
        build_id: int,
):
    with get_sync_db() as db:
        try:
            await distro_crud.modify_distribution(
                build_id, distribution, db, 'add')
            return {'success': True}
        except DistributionError as error:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                                detail=str(error))


@router.post('/remove/{build_id}/{distribution}/',
             response_model=typing.Dict[str, bool])
async def remove_from_distribution(
        distribution: str,
        build_id: int,
):
    with get_sync_db() as db:
        try:
            await distro_crud.modify_distribution(
                build_id, distribution, db, 'remove')
            return {'success': True}
        except DistributionError as error:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                                detail=str(error))


@router.get('/', response_model=typing.List[distro_schema.Distribution])
async def get_distributions():
    with get_sync_db() as db:
        return await distro_crud.get_distributions(db)

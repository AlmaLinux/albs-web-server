import typing

from fastapi import APIRouter, Depends, FastAPI

from alws.dependencies import get_db, JWTBearer
from alws import database, crud
from alws.schemas import distro_schema

app = FastAPI()
router = APIRouter(
    prefix='/distro',
    tags=['distro'],
    dependencies=[Depends(JWTBearer())]
)


@router.post('/new/', response_model=distro_schema.Distribution)
async def create_distribution(
        distribution: distro_schema.DistroCreate,
        db: database.Session = Depends(get_db)):
    return await crud.create_distro(db, distribution)


@router.post('/add/{build_id}/{distribution}/', response_model=bool)
async def add_to_distribution(
        distribution: str,
        build_id: int,
        db: database.Session = Depends(get_db)
):
    return await crud.modify_distribution(build_id, distribution, db, 'add')


@router.post('/remove/{build_id}/{distribution}/', response_model=bool)
async def add_to_distribution(
        distribution: str,
        build_id: int,
        db: database.Session = Depends(get_db)
):
    return await crud.modify_distribution(build_id, distribution,
                                          db, 'remove')


@router.get('/', response_model=typing.List[distro_schema.Distribution])
async def get_distributions(
        db: database.Session = Depends(get_db)
):
    return await crud.get_distributions(db)

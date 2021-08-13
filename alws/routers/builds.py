import typing

from fastapi import APIRouter, Depends, HTTPException, status

from alws.dependencies import get_db, JWTBearer
from alws import database, crud
from alws.schemas import build_schema


router = APIRouter(
    prefix='/builds',
    tags=['builds'],
    dependencies=[Depends(JWTBearer())]
)


@router.post('/', response_model=build_schema.Build)
async def create_build(
            build: build_schema.BuildCreate,
            user: dict = Depends(JWTBearer()),
            db: database.Session = Depends(get_db)
        ):
    db_build = await crud.create_build(db, build, user['identity']['user_id'])
    return db_build


@router.get('/', response_model=typing.List[build_schema.Build])
async def get_builds(db: database.Session = Depends(get_db)):
    return await crud.get_builds(db)


@router.get('/{build_id}/', response_model=build_schema.Build)
async def get_build(build_id: int, db: database.Session = Depends(get_db)):
    db_build = await crud.get_builds(db, build_id)
    if db_build is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f'Build with {build_id=} is not found'
        )
    return db_build

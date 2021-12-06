import typing

from fastapi import APIRouter, Depends

from alws import database
from alws.crud import release as r_crud
from alws.dependencies import get_db, JWTBearer
from alws.schemas import release_schema


router = APIRouter(
    prefix='/releases',
    tags=['releases'],
    dependencies=[Depends(JWTBearer())]
)


@router.get('/', response_model=typing.List[release_schema.Release])
async def get_releases(db: database.Session = Depends(get_db)):
    return await r_crud.get_releases(db)


@router.post('/new/', response_model=release_schema.Release)
async def create_new_release(builds: release_schema.ReleaseCreate,
                             db: database.Session = Depends(get_db),
                             user: dict = Depends(JWTBearer())):
    release = await r_crud.create_new_release(
        db, user['identity']['user_id'], builds)
    return release


@router.put('/{release_id}/', response_model=release_schema.Release)
async def update_release(release_id: int,
                         payload: release_schema.ReleaseUpdate,
                         db: database.Session = Depends(get_db)):
    return await r_crud.update_release(db, release_id, payload)


@router.post('/{release_id}/commit/',
             response_model=release_schema.ReleaseCommitResult)
async def commit_release(release_id: int,
                         db: database.Session = Depends(get_db)):
    release, message = await r_crud.commit_release(db, release_id)
    return {'release': release, 'message': message}

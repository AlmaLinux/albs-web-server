import typing

from fastapi import APIRouter, Depends

from alws.crud import release as r_crud
from alws.dependencies import JWTBearer, get_sync_db
from alws.schemas import release_schema


router = APIRouter(
    prefix='/releases',
    tags=['releases'],
    dependencies=[Depends(JWTBearer())]
)


@router.get('/', response_model=typing.List[release_schema.Release])
async def get_releases():
    with get_sync_db() as db:
        return await r_crud.get_releases(db)


@router.post('/new/', response_model=release_schema.Release)
async def create_new_release(payload: release_schema.ReleaseCreate,
                             user: dict = Depends(JWTBearer())):
    with get_sync_db() as db:
        release = await r_crud.create_new_release(
            db, user['identity']['user_id'], payload)
        return release


@router.put('/{release_id}/', response_model=release_schema.Release)
async def update_release(release_id: int,
                         payload: release_schema.ReleaseUpdate):
    with get_sync_db() as db:
        return await r_crud.update_release(db, release_id, payload)


@router.post('/{release_id}/commit/',
             response_model=release_schema.ReleaseCommitResult)
async def commit_release(release_id: int):
    with get_sync_db() as db:
        release, message = await r_crud.commit_release(db, release_id)
        return {'release': release, 'message': message}

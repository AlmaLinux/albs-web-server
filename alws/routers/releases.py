import typing

from sqlalchemy import update
from fastapi import APIRouter, Depends, Request

from alws import database, models
from alws.auth import get_current_user
from alws.crud import release as r_crud
from alws.dependencies import get_db
from alws.schemas import release_schema
from alws.dramatiq import execute_release_plan
from alws.constants import ReleaseStatus


router = APIRouter(
    prefix='/releases',
    tags=['releases'],
    dependencies=[Depends(get_current_user)]
)


# TODO: add pulp db loader
@router.get(
    '/',
    response_model=typing.Union[
        typing.List[release_schema.Release],
        release_schema.ReleaseResponse
    ],
)
async def get_releases(
    request: Request,
    pageNumber: int = None,
    db: database.Session = Depends(get_db),
):
    search_params = release_schema.ReleaseSearch(**request.query_params)
    return await r_crud.get_releases(
        db,
        page_number=pageNumber,
        search_params=search_params,
    )


@router.get('/{release_id}/', response_model=release_schema.Release)
async def get_release(
    release_id: int,
    db: database.Session = Depends(get_db),
):
    return await r_crud.get_releases(db, release_id=release_id)


@router.post('/new/', response_model=release_schema.Release)
async def create_new_release(payload: release_schema.ReleaseCreate,
                             db: database.Session = Depends(get_db),
                             user: models.User = Depends(get_current_user)):
    release = await r_crud.create_release(db, user.id, payload)
    return release


@router.put('/{release_id}/', response_model=release_schema.Release)
async def update_release(release_id: int,
                         payload: release_schema.ReleaseUpdate,
                         db: database.Session = Depends(get_db),
                         user: models.User = Depends(get_current_user),
                         ):
    release = await r_crud.update_release(db, release_id, user.id, payload)
    return release


@router.post('/{release_id}/commit/',
             response_model=release_schema.ReleaseCommitResult)
async def commit_release(
    release_id: int,
    db: database.Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    # it's ugly hack for updating release status before execution in background
    async with db.begin():
        await db.execute(update(models.Release).where(
            models.Release.id == release_id,
        ).values(status=ReleaseStatus.IN_PROGRESS))
    execute_release_plan.send(release_id, user.id)
    return {'message': 'Release plan execution has been started'}

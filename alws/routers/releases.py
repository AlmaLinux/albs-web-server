import typing

from sqlalchemy import update
from fastapi import APIRouter, Depends

from alws import database
from alws.crud import release as r_crud
from alws.dependencies import get_db, get_pulp_db, JWTBearer
from alws.schemas import release_schema
from alws.release_planner import ReleasePlanner
from alws.dramatiq import execute_release_plan
from alws import models
from alws.constants import ReleaseStatus


router = APIRouter(
    prefix='/releases',
    tags=['releases'],
    dependencies=[Depends(JWTBearer())]
)


# TODO: add pulp db loader
@router.get('/', response_model=typing.Union[
    typing.List[release_schema.Release],
    release_schema.ReleaseResponse])
async def get_releases(pageNumber: int = None,
                       db: database.Session = Depends(get_db)):
    return await r_crud.get_releases(pageNumber, db)


@router.post('/new/', response_model=release_schema.Release)
async def create_new_release(payload: release_schema.ReleaseCreate,
                             db: database.Session = Depends(get_db),
                             pulp_db: database.Session = Depends(get_pulp_db),
                             user: dict = Depends(JWTBearer())):
    release_planner = ReleasePlanner(db, pulp_db)
    release = await release_planner.create_new_release(
        user['identity']['user_id'], payload)
    return release


@router.put('/{release_id}/', response_model=release_schema.Release)
async def update_release(release_id: int,
                         payload: release_schema.ReleaseUpdate,
                         db: database.Session = Depends(get_db),
                         pulp_db: database.Session = Depends(get_pulp_db),
                         ):
    release_planner = ReleasePlanner(db, pulp_db)
    return await release_planner.update_release(release_id, payload)


@router.post('/{release_id}/commit/',
             response_model=release_schema.ReleaseCommitResult)
async def commit_release(
    release_id: int,
    db: database.Session = Depends(get_db),
):
    # it's ugly hack for updating release status before execution in background
    async with db.begin():
        await db.execute(update(models.Release).where(
            models.Release.id == release_id,
        ).values(status=ReleaseStatus.IN_PROGRESS))
    execute_release_plan.send(release_id)
    return {'message': 'Release plan execution has been started'}

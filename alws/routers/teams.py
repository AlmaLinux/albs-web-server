import typing

from fastapi import APIRouter, Depends

from alws import database
from alws.auth import get_current_user
from alws.crud import teams
from alws.dependencies import get_db
from alws.schemas import team_schema


router = APIRouter(
    prefix='/teams',
    tags=['teams'],
    dependencies=[Depends(get_current_user)]
)


@router.get('/', response_model=typing.List[team_schema.Team])
async def get_teams(db: database.Session = Depends(get_db)):
    return await teams.get_teams(db)

import typing

from fastapi import APIRouter, Depends

from alws import database
from alws.crud import teams
from alws.dependencies import get_db, JWTBearer
from alws.schemas import team_schema


router = APIRouter(
    prefix='/teams',
    tags=['teams'],
    dependencies=[Depends(JWTBearer())]
)


@router.get('/', response_model=typing.List[team_schema.Team])
async def get_teams(db: database.Session = Depends(get_db)):
    return await teams.get_teams(db)

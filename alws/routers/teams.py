import typing

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    status,
)

from alws import database
from alws.crud import teams
from alws.dependencies import get_db, JWTBearer
from alws.errors import TeamError
from alws.schemas import team_schema


router = APIRouter(
    prefix='/teams',
    tags=['teams'],
    dependencies=[Depends(JWTBearer())]
)


@router.get('/', response_model=typing.Union[
    typing.List[team_schema.Team], team_schema.TeamResponse])
async def get_teams(
    pageNumber: int = None,
    db: database.Session = Depends(get_db),
):
    return await teams.get_teams(db, page_number=pageNumber)


@router.get('/{team_id}/', response_model=team_schema.Team)
async def get_team(
    team_id: int,
    db: database.Session = Depends(get_db),
):
    return await teams.get_teams(db, team_id=team_id)


@router.post('/{team_id}/members/', response_model=team_schema.Team)
async def update_members(
    team_id: int,
    payload: team_schema.TeamMembersUpdate,
    db: database.Session = Depends(get_db),
):
    try:
        db_team = await teams.update_members(db, payload, team_id)
    except TeamError as exc:
        raise HTTPException(
            detail=str(exc),
            status_code=status.HTTP_400_BAD_REQUEST,
        )
    return await teams.get_teams(db, team_id=db_team.id)


@router.post('/create/', response_model=team_schema.Team)
async def create_team(
    payload: team_schema.TeamCreate,
    db: database.Session = Depends(get_db),
):
    try:
        db_team = await teams.create_team(db, payload)
    except TeamError as exc:
        raise HTTPException(
            detail=str(exc),
            status_code=status.HTTP_400_BAD_REQUEST,
        )
    return await teams.get_teams(db, team_id=db_team.id)


@router.delete('/{team_id}/remove/', status_code=status.HTTP_202_ACCEPTED)
async def remove_team(
    team_id: int,
    db: database.Session = Depends(get_db)
):
    try:
        await teams.remove_team(db, team_id)
    except TeamError as exc:
        raise HTTPException(
            detail=str(exc),
            status_code=status.HTTP_400_BAD_REQUEST,
        )

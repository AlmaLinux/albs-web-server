import typing

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    status,
)
from fastapi_sqla.asyncio_support import AsyncSession

from alws.auth import get_current_superuser
from alws.crud import teams
from alws.errors import TeamError
from alws.schemas import team_schema


router = APIRouter(
    prefix='/teams',
    tags=['teams'],
    dependencies=[Depends(get_current_superuser)]
)

public_router = APIRouter(
    prefix='/teams',
    tags=['teams'],
)


@public_router.get('/', response_model=typing.Union[
    typing.List[team_schema.Team], team_schema.TeamResponse])
async def get_teams(
    pageNumber: int = None,
    db: AsyncSession = Depends(),
):
    return await teams.get_teams(db, page_number=pageNumber)


@public_router.get('/{team_id}/', response_model=team_schema.Team)
async def get_team(
    team_id: int,
    db: AsyncSession = Depends(),
):
    return await teams.get_teams(db, team_id=team_id)


@router.post('/{team_id}/members/add/', response_model=team_schema.Team)
async def add_members(
    team_id: int,
    payload: team_schema.TeamMembersUpdate,
    db: AsyncSession = Depends(),
):
    try:
        db_team = await teams.update_members(db, payload, team_id, 'add')
    except TeamError as exc:
        raise HTTPException(
            detail=str(exc),
            status_code=status.HTTP_400_BAD_REQUEST,
        )
    return await teams.get_teams(db, team_id=db_team.id)


@router.post('/{team_id}/members/remove/', response_model=team_schema.Team)
async def remove_members(
    team_id: int,
    payload: team_schema.TeamMembersUpdate,
    db: AsyncSession = Depends(),
):
    try:
        db_team = await teams.update_members(db, payload, team_id, 'remove')
    except TeamError as exc:
        raise HTTPException(
            detail=str(exc),
            status_code=status.HTTP_400_BAD_REQUEST,
        )
    return await teams.get_teams(db, team_id=db_team.id)


@router.post('/create/', response_model=team_schema.Team)
async def create_team(
    payload: team_schema.TeamCreate,
    db: AsyncSession = Depends(),
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
    db: AsyncSession = Depends(),
):
    try:
        await teams.remove_team(db, team_id)
    except TeamError as exc:
        raise HTTPException(
            detail=str(exc),
            status_code=status.HTTP_400_BAD_REQUEST,
        )

import typing

from alws.schemas.role_schema import Role
from alws.schemas.user_schema import User
from pydantic import BaseModel

__all__ = ['Team', 'TeamCreate']


class TeamCreate(BaseModel):
    team_name: str
    user_id: int


class TeamProduct(BaseModel):
    id: int
    name: str
    title: typing.Optional[str] = None

    class Config:
        from_attributes = True


class Team(BaseModel):
    id: int
    name: str
    members: typing.Optional[typing.List[User]] = None
    owner: typing.Optional[User] = None
    products: typing.List[TeamProduct] = []
    roles: typing.Optional[typing.List[Role]] = None

    class Config:
        from_attributes = True


class TeamResponse(BaseModel):
    teams: typing.List[Team]
    total_teams: typing.Optional[int] = None
    current_page: typing.Optional[int] = None


class TeamMembersUpdate(BaseModel):
    members_to_update: typing.List[User] = []

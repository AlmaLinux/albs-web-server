import typing

from pydantic import BaseModel

from alws.schemas.user_schema import User
from alws.schemas.role_schema import Role


__all__ = ['Team']


class TeamCreate(BaseModel):
    team_name: str
    user_id: int


class TeamProduct(BaseModel):
    id: int
    name: str

    class Config:
        orm_mode = True


class Team(BaseModel):
    id: int
    name: str
    members: typing.Optional[typing.List[User]]
    owner: typing.Optional[User]
    products: typing.List[TeamProduct] = []
    roles: typing.Optional[typing.List[Role]]

    class Config:
        orm_mode = True


class TeamResponse(BaseModel):
    teams: typing.List[Team]
    total_teams: typing.Optional[int]
    current_page: typing.Optional[int]


class TeamMembersUpdate(BaseModel):
    modification: str
    members_to_update: typing.List[User] = []

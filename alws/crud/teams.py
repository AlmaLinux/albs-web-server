from sqlalchemy.future import select
from sqlalchemy.orm import selectinload

from alws.crud.actions import ensure_all_actions_exist
from alws.database import Session
from alws.models import (
    Team,
    User,
    UserAction,
    UserRole,
)
from alws.perms.roles import (
    Contributor,
    Manager,
    Observer,
    PlatformMaintainer,
    ProductMaintainer,
    Signer,
)


async def create_team_roles(session: Session, team_name: str):
    required_roles = (Contributor, Manager, Observer, PlatformMaintainer,
                      ProductMaintainer, Signer)
    new_role_names = [f'{team_name}_{role.name}'
                      for role in required_roles]

    existing_roles = (await session.execute(select(UserRole).where(
        UserRole.name.in_(new_role_names)))).scalars().all()
    existing_role_names = {r.name for r in existing_roles}

    if len(new_role_names) == len(existing_roles):
        return existing_roles

    await ensure_all_actions_exist(session)
    existing_actions = (await session.execute(
        select(UserAction))).scalars().all()

    new_roles = []
    for role in required_roles:
        role_name = f'{team_name}_{role.name}'
        if role_name in existing_role_names:
            continue
        role_actions = []
        for required_action in role.actions:
            for action in existing_actions:
                if required_action == action.name:
                    role_actions.append(action)

        new_roles.append(UserRole(name=role_name, actions=role_actions))

    if new_roles:
        session.add_all(new_roles)
        await session.flush()

    for role in new_roles:
        await session.refresh(role)

    return new_roles + existing_roles


async def create_team(session: Session, team_name: str, user_id: int) -> Team:
    owner = (await session.execute(select(User).where(
        User.id == user_id).options(
        selectinload(User.roles)
    ))).scalars().first()

    if not owner:
        raise ValueError(f'Unknown user ID: {user_id}')

    existing_team = (await session.execute(select(Team).where(
        Team.name == team_name).options(
        selectinload(Team.roles),
        selectinload(Team.owner),
        selectinload(Team.members),
    ))).scalars().first()

    if existing_team:
        return existing_team

    team_roles = await create_team_roles(session, team_name)
    manager_role = [r for r in team_roles if 'manager' in r.name][0]

    new_team = Team(name=team_name)
    new_team.owner = owner
    new_team.roles = team_roles
    new_team.members = [owner]
    owner.roles.append(manager_role)

    session.add(new_team)
    session.add_all(team_roles)
    session.add(owner)
    await session.commit()
    await session.refresh(new_team)
    return new_team


async def get_teams(session: Session):
    return (await session.execute(select(Team).options(
        selectinload(Team.members),
        selectinload(Team.owner),
        selectinload(Team.roles)
    ))).scalars().all()

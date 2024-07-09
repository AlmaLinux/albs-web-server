import typing

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.orm import selectinload
from sqlalchemy.sql.expression import func

from alws.crud.actions import ensure_all_actions_exist
from alws.errors import TeamError
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
    ProductMaintainer,
    Signer,
)
from alws.schemas import team_schema

__all__ = [
    'create_team',
    'create_team_roles',
    'get_team_role_name',
    'get_teams',
]


from alws.perms.authorization import can_perform
from alws.errors import (
    PermissionDenied,
)
from alws.perms import actions
from alws.perms.actions import (
    CreateTeam,
    DeleteTeam,
    InviteToTeam,
    LeaveTeam,
    ReadTeam,
    RemoveFromTeam,
    UpdateTeam,
)
from alws.models import (
    Team,
    User,
    UserAction,
    UserRole,
)
from alws.crud.actions import ensure_all_actions_exist
from alws.crud.user import get_user


def get_team_role_name(team_name: str, role_name: str):
    return f'{team_name}_{role_name}'


async def create_team_roles(session: AsyncSession, team_name: str):
    required_roles = (
        Contributor,
        Manager,
        Observer,
        ProductMaintainer,
        Signer,
    )
    new_role_names = [
        get_team_role_name(team_name, role.name) for role in required_roles
    ]

    existing_roles = (
        (
            await session.execute(
                select(UserRole).where(UserRole.name.in_(new_role_names))
            )
        )
        .scalars()
        .all()
    )
    existing_role_names = {r.name for r in existing_roles}

    if len(new_role_names) == len(existing_roles):
        return existing_roles

    await ensure_all_actions_exist(session)
    existing_actions = (
        (await session.execute(select(UserAction))).scalars().all()
    )

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


async def create_team(
    session: AsyncSession,
    payload: team_schema.TeamCreate,
    flush: bool = False,
) -> Team:
    owner = (
        (
            await session.execute(
                select(User)
                .where(User.id == payload.user_id)
                .options(selectinload(User.roles))
            )
        )
        .scalars()
        .first()
    )

    if not owner:
        raise TeamError(f'Unknown user ID: {payload.user_id}')

    existing_team = (
        (
            await session.execute(
                select(Team)
                .where(Team.name == payload.team_name)
                .options(
                    selectinload(Team.roles),
                    selectinload(Team.owner),
                    selectinload(Team.members),
                )
            )
        )
        .scalars()
        .first()
    )

    if existing_team:
        raise TeamError(f'Team={payload.team_name} already exist')

    team_roles = await create_team_roles(session, payload.team_name)
    manager_role = [r for r in team_roles if 'manager' in r.name][0]

    new_team = Team(name=payload.team_name)
    new_team.owner = owner
    new_team.roles = team_roles
    new_team.members = [owner]
    owner.roles.append(manager_role)

    session.add(new_team)
    session.add_all(team_roles)
    session.add(owner)
    await session.flush()
    await session.refresh(new_team)
    return new_team


async def get_teams(
    session: AsyncSession,
    page_number: int = None,
    team_id: int = None,
    name: str = None,
) -> typing.Union[typing.List[Team], typing.Dict[str, typing.Any], Team]:

    def generate_query(count=False):
        query = (
            select(Team)
            .order_by(Team.id.desc())
            .options(
                selectinload(Team.members),
                selectinload(Team.owner),
                selectinload(Team.roles).selectinload(UserRole.actions),
                selectinload(Team.products),
            )
        )
        if name:
            query = query.where(Team.name == name)
        if count:
            query = select(func.count(Team.id))
        if page_number and not count:
            query = query.slice(10 * page_number - 10, 10 * page_number)
        return query

    if page_number:
        return {
            'teams': (await session.execute(generate_query())).scalars().all(),
            'total_teams': (
                await session.execute(generate_query(count=True))
            ).scalar(),
            'current_page': page_number,
        }
    if team_id:
        query = generate_query().where(Team.id == team_id)
        db_team = (await session.execute(query)).scalars().first()
        db_team.members = sorted(db_team.members, key=lambda x: x.id)
        return db_team
    return (await session.execute(generate_query())).scalars().all()


async def update_members(
    session: AsyncSession,
    payload: team_schema.TeamMembersUpdate,
    team_id: int,
    modification: str,
    user_id: int,
) -> Team:
    items_to_update = []
    db_team = (
        (
            await session.execute(
                select(Team)
                .where(Team.id == team_id)
                .options(
                    selectinload(Team.members),
                    selectinload(Team.owner),
                    selectinload(Team.roles),
                ),
            )
        )
        .scalars()
        .first()
    )
    if not db_team:
        raise TeamError(f'Team={team_id} doesn`t exist')

    db_user = await get_user(session, user_id=user_id)

    if not can_perform(db_team, db_user, actions.UpdateTeam.name):
        raise PermissionDenied(
            f"User has no permissions to update the team {db_team.name}"
        )

    db_users = await session.execute(
        select(User)
        .where(User.id.in_((user.id for user in payload.members_to_update)))
        .options(selectinload(User.roles), selectinload(User.oauth_accounts)),
    )
    db_contributor_team_role = next(
        role for role in db_team.roles if Contributor.name in role.name
    )
    operation = 'append' if modification == 'add' else 'remove'
    db_team_members_update_operation = getattr(db_team.members, operation)
    for db_user in db_users.scalars().all():
        if operation == 'remove' and db_user not in db_team.members:
            raise TeamError(
                f'Cannot remove user={db_user.id} from team,'
                ' user not in team members'
            )
        db_user_role_update_operation = getattr(db_user.roles, operation)
        db_team_members_update_operation(db_user)
        db_user_role_update_operation(db_contributor_team_role)
        if operation == 'remove':
            for user_role in db_user.roles:
                if user_role in db_team.roles:
                    db_user_role_update_operation(user_role)
        items_to_update.append(db_user)
    items_to_update.append(db_team)
    session.add_all(items_to_update)
    await session.flush()
    await session.refresh(db_team)
    return db_team


async def remove_team(
        db: AsyncSession,
        team_id: int,
        user_id: int,
):
    db_team = await get_teams(db, team_id=team_id)
    db_user = await get_user(db, user_id=user_id)

    if not db_team:
        raise TeamError(f'Team={team_id} doesn`t exist')

    if not can_perform(db_team, db_user, actions.DeleteTeam.name):
        raise PermissionDenied(
            f"User has no permissions to delete the team {db_team.name}"
        )

    if db_team.products:
        raise TeamError(
            f"Cannot delete Team={team_id}, team contains undeleted products",
        )
    await db.delete(db_team)
    await db.flush()

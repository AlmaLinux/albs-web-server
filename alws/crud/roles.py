import typing

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.orm import selectinload

from alws import models
from alws.perms.roles import RolesList

__all__ = [
    'get_roles',
    'fix_roles_actions',
]


async def get_roles(db: AsyncSession) -> typing.List[models.UserRole]:
    return (await db.execute(select(models.UserRole))).scalars().all()


async def fix_roles_actions(db: AsyncSession, commit: bool = False):
    actions = (await db.execute(select(models.UserAction))).scalars().all()
    roles = (
        (
            await db.execute(
                select(models.UserRole).options(
                    selectinload(models.UserRole.actions)
                )
            )
        )
        .scalars()
        .all()
    )

    roles_list = [
        {'name': r.name, 'actions': set(r.actions)} for r in RolesList
    ]
    new_roles = []

    for role in roles:
        r_actions = None
        for act_role in roles_list:
            if role.name.endswith(act_role['name']):
                r_actions = set(act_role['actions'])
                break
        if not r_actions:
            raise ValueError(f'No actions found for the role {role.name}')

        required_actions_mapping = {
            a.name: a for a in actions if a.name in r_actions
        }
        current_actions = {a.name for a in role.actions}
        for action_name, action in required_actions_mapping.items():
            if action_name not in current_actions:
                role.actions.append(action)

        new_roles.append(role)

    db.add_all(new_roles)
    await db.flush()

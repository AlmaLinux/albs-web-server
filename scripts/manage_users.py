import argparse
import asyncio
import os
import sys
from contextlib import asynccontextmanager

from sqlalchemy import delete
from sqlalchemy.future import select
from sqlalchemy.orm import selectinload

sys.path.append(os.path.dirname(os.path.dirname(__file__)))

from alws import models
from alws.crud import (
    actions as action_crud,
    roles as role_crud,
    teams as team_crud, user as user_crud,
)
from alws.dependencies import get_db
from alws.perms.roles import RolesList


def parse_args():
    role_names = [r.name for r in RolesList]
    parser = argparse.ArgumentParser(
        'manage_users',
        description='Script to manage users and roles for them')
    parser.add_argument('-e', '--email', required=True, type=str,
                        help='User e-mail')
    parser.add_argument('-t', '--team-name', required=False, type=str,
                        help='Team name')
    parser.add_argument('-a', '--add-role', required=False, action='append',
                        dest='add_roles', type=str, help='Add role(s)',
                        choices=role_names)
    parser.add_argument('-r', '--remove-role', required=False, action='append',
                        dest='remove_roles', type=str, help='Remove role(s)',
                        choices=role_names)
    parser.add_argument('-v', '--verify', required=False, action='store_true',
                        help='Verify user')
    parser.add_argument('-d', '--deactivate', required=False,
                        action='store_true', help='Deactivate user')
    parser.add_argument('-S', '--superuser', required=False,
                        action='store_true', help='Make user a superuser')
    parser.add_argument('-u', '--usual-user', required=False,
                        action='store_true', help='Make user a usual one')
    parser.add_argument('-f', '--fix', required=False, action='store_true',
                        help='Fix roles and actions')
    return parser.parse_args()


async def main() -> int:
    arguments = parse_args()
    async with asynccontextmanager(get_db)() as db, db.begin():
        user = (await db.execute(select(models.User).where(
            models.User.email == arguments.email).options(
            selectinload(models.User.roles),
            selectinload(models.User.oauth_accounts),
        ))).scalars().first()
        if not user:
            raise ValueError(f'No such user in the system: '
                             f'{arguments.email}')

        if arguments.verify and arguments.deactivate:
            raise ValueError('Cannot both activate and deactivate user')

        if arguments.superuser and arguments.usual_user:
            raise ValueError('Cannot both make user a superuser '
                             'and usual one')

        if arguments.fix:
            await action_crud.ensure_all_actions_exist(db)
            await role_crud.fix_roles_actions(db)

        # ALBS-643: Use user crud update_user function
        # to activate/deactivate and grant/revoke superuser
        # permissions to users
        if arguments.verify:
            await user_crud.activate_user(user.id, db)

        if arguments.deactivate:
            await user_crud.deactivate_user(user.id, db)

        if arguments.superuser:
            await user_crud.make_superuser(user.id, db)

        if arguments.usual_user:
            await user_crud.make_usual_user(user.id, db)

        if (arguments.add_roles or
            arguments.remove_roles) and not arguments.team_name:
            print('Cannot assign roles without team specified, exiting')
            return 1

        team = (await db.execute(select(models.Team).where(
            models.Team.name == arguments.team_name))).scalars().first()
        if not team:
            raise ValueError(f'No such team in the system: '
                             f'{arguments.team_name}')

        add_roles = None
        remove_roles = None

        if arguments.add_roles:
            add_roles = (await db.execute(select(models.UserRole).where(
                models.UserRole.name.in_(
                    [team_crud.get_team_role_name(team.name, r)
                     for r in arguments.add_roles]))
            )).scalars().all()

        if arguments.remove_roles:
            remove_roles = (await db.execute(select(models.UserRole).where(
                models.UserRole.name.in_(
                    [team_crud.get_team_role_name(team.name, r)
                     for r in arguments.remove_roles]))
            )).scalars().all()

        if add_roles:
            user.roles.extend(add_roles)
        if remove_roles:
            roles_ids = [r.id for r in remove_roles]
            await db.execute(delete(models.UserRoleMapping).where(
                models.UserRoleMapping.c.role_id.in_(roles_ids),
                models.UserRoleMapping.c.user_id == user.id
            ))

        db.add(user)
    return 0


if __name__ == '__main__':
    result = asyncio.run(main())
    sys.exit(result)

import argparse
import asyncio
import os
import sys

from sqlalchemy import delete
from sqlalchemy.future import select
from sqlalchemy.orm import selectinload

sys.path.append(os.path.dirname(os.path.dirname(__file__)))

from alws import models
from alws.crud import teams as team_crud
from alws.dependencies import get_db
from alws.perms.roles import RolesList


def parse_args():
    role_names = [r.name for r in RolesList]
    parser = argparse.ArgumentParser(
        'manage_team_roles_for_user',
        description='Script to manage roles for user on per-team basis')
    parser.add_argument('-t', '--team-name', required=True, type=str,
                        help='Team name')
    parser.add_argument('-e', '--email', required=True, type=str,
                        help='User e-mail')
    parser.add_argument('-a', '--add-role', required=False, action='append',
                        dest='add_roles', type=str, help='Add role(s)',
                        choices=role_names)
    parser.add_argument('-r', '--remove-role', required=False, action='append',
                        dest='remove_roles', type=str, help='Add role(s)',
                        choices=role_names)
    return parser.parse_args()


async def main():
    arguments = parse_args()
    async for db in get_db():
        async with db.begin():
            team = (await db.execute(select(models.Team).where(
                models.Team.name == arguments.team_name))).scalars().first()
            if not team:
                raise ValueError(f'No such team in the system: '
                                 f'{arguments.team_name}')

            user = (await db.execute(select(models.User).where(
                models.User.email == arguments.email).options(
                selectinload(models.User.roles),
                selectinload(models.User.oauth_accounts),
            ))).scalars().first()
            if not team:
                raise ValueError(f'No such user in the system: '
                                 f'{arguments.email}')

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
                    models.UserRoleMapping.c.role_id.in_(roles_ids)))

            db.add(user)


if __name__ == '__main__':
    asyncio.run(main())

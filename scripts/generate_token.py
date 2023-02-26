import argparse
import asyncio
import contextlib
import sys
import os

from fastapi_users.authentication.strategy import JWTStrategy
from sqlalchemy.future import select
from sqlalchemy.orm import selectinload
from syncer import sync

sys.path.append(os.path.dirname(os.path.dirname(__file__)))

from alws.dependencies import get_db
from alws.auth.dependencies import get_user_db
from alws.auth.user_manager import get_user_manager
from alws.constants import SYSTEM_USER_NAME, DEFAULT_TEAM
from alws.models import User, SignKey, UserRole
from alws.crud.actions import ensure_all_actions_exist
from alws.crud.teams import create_team_roles


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument('-e', '--email', required=False, type=str,
                        default=None,
                        help='User e-mail')
    parser.add_argument('-u', '--username', required=False, type=str,
                        default=None,
                        help='User e-mail')
    parser.add_argument('-s', '--secret', required=True, type=str,
                        help='JWT secret')
    return parser.parse_args(sys.argv[1:])


async def gen_token(secret: str, email: str = None, username: str = None):
    strategy = JWTStrategy(secret, lifetime_seconds=2678400)
    get_async_session_context = contextlib.asynccontextmanager(get_db)
    get_user_db_context = contextlib.asynccontextmanager(get_user_db)
    get_user_manager_context = contextlib.asynccontextmanager(get_user_manager)
    async with get_async_session_context() as session:
        conds = []
        if email:
            conds.append(User.email == email)
        if username:
            conds.append(User.username == username)
        if not email and not username:
            raise ValueError("Need to specify either email or username")
        user = (await session.execute(select(User).where(*conds))).scalars().first()
        async with get_user_db_context(session) as user_db:
            async with get_user_manager_context(user_db) as user_manager:
                res = await strategy.write_token(user)
                print(res)


def main():
    arguments = parse_args()
    asyncio.run(gen_token(arguments.secret, email=arguments.email, username=arguments.username))


if __name__ == '__main__':
    main()


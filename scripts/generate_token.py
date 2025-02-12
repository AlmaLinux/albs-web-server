import argparse
import asyncio
import contextlib
import os
import sys

from fastapi_sqla import open_async_session
from fastapi_users.authentication.strategy import JWTStrategy
from sqlalchemy.future import select

sys.path.append(os.path.dirname(os.path.dirname(__file__)))

from alws.auth.dependencies import get_async_db_key, get_user_db
from alws.auth.user_manager import get_user_manager
from alws.models import User
from alws.utils.fastapi_sqla_setup import setup_all


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        '-e',
        '--email',
        required=False,
        type=str,
        default=None,
        help='User e-mail',
    )
    parser.add_argument(
        '-u',
        '--username',
        required=False,
        type=str,
        default=None,
        help='User e-mail',
    )
    parser.add_argument(
        '-s', '--secret', required=True, type=str, help='JWT secret'
    )
    return parser.parse_args(sys.argv[1:])


async def gen_token(secret: str, email: str = None, username: str = None):
    await setup_all()

    strategy = JWTStrategy(secret, lifetime_seconds=1 * 31557600)
    get_async_session_context = open_async_session(key=get_async_db_key())
    get_user_db_context = contextlib.asynccontextmanager(get_user_db)
    get_user_manager_context = contextlib.asynccontextmanager(get_user_manager)
    async with get_async_session_context as session:
        conds = []
        if email:
            conds.append(User.email == email)
        if username:
            conds.append(User.username == username)
        if not email and not username:
            raise ValueError("Need to specify either email or username")
        user = (
            (await session.execute(select(User).where(*conds)))
            .scalars()
            .first()
        )
        async with get_user_db_context(session) as user_db:
            async with get_user_manager_context(user_db):
                res = await strategy.write_token(user)
                print(res)


def main():
    arguments = parse_args()
    asyncio.run(
        gen_token(
            arguments.secret,
            email=arguments.email,
            username=arguments.username,
        )
    )


if __name__ == '__main__':
    main()

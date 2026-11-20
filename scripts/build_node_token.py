"""Issue and revoke the tokens of the build nodes.

A build node token belongs to a build node service user (users.is_build_node):
it's accepted by /api/v1/build_node/* only. A new user is shared by any nodes
unless --node-name binds it to one node, then its tokens are accepted with this
node_name only.

    # A token shared by several nodes
    python3 scripts/build_node_token.py -u build-nodes
    # A token of node-a only
    python3 scripts/build_node_token.py -u build-node-a -n node-a
    # Revoke all the tokens of a user
    python3 scripts/build_node_token.py -u build-node-a --revoke

The tokens don't expire unless --lifetime-days is given, a token is revoked by
revoking its user. The token is printed to stdout, everything else to stderr.
Running the script again for an existing user issues one more token of it with
the binding of the user; the earlier ones stay valid. The JWT secret is the one
of the server settings (JWT_SECRET), --secret overrides it.
"""

import argparse
import asyncio
import contextlib
import os
import sys
import typing

from fastapi_sqla import open_async_session
from fastapi_users.authentication.strategy import JWTStrategy
from sqlalchemy.future import select

sys.path.append(os.path.dirname(os.path.dirname(__file__)))

from alws.config import settings
from alws.dependencies import get_async_db_key
from alws.models import User
from alws.utils.fastapi_sqla_setup import setup_all

EMAIL_DOMAIN = 'build-nodes.invalid'


def parse_args(argv: typing.Optional[typing.List[str]] = None):
    parser = argparse.ArgumentParser(
        'build_node_token',
        description='Issue or revoke the tokens of a build node service user',
    )
    parser.add_argument(
        '-u',
        '--username',
        required=True,
        help='Build node service user, created if it does not exist',
    )
    parser.add_argument(
        '-e',
        '--email',
        help=f'E-mail of a new user, <username>@{EMAIL_DOMAIN} by default',
    )
    parser.add_argument(
        '-n',
        '--node-name',
        help='Bind a new user to this build_node_name, '
        'a new user is shared by any nodes without it',
    )
    parser.add_argument(
        '-s',
        '--secret',
        default=settings.jwt_secret,
        help='JWT secret, the one of the server settings by default',
    )
    parser.add_argument(
        '--lifetime-days',
        type=float,
        help='Token lifetime in days, the token does not expire without it',
    )
    parser.add_argument(
        '--revoke',
        action='store_true',
        help='Deactivate the user, which revokes all its tokens',
    )
    args = parser.parse_args(argv)
    if not args.revoke and not args.secret:
        parser.error('No JWT secret in the settings, use --secret')
    if args.lifetime_days is not None and args.lifetime_days <= 0:
        parser.error('--lifetime-days must be positive')
    return args


def log(message: str):
    print(message, file=sys.stderr)


def check_existing_user(user: User, node_name: typing.Optional[str]):
    if not user.is_build_node:
        raise SystemExit(
            f'User {user.username} is not a build node user, '
            'choose another username'
        )
    if user.is_superuser:
        raise SystemExit(
            f'User {user.username} is a superuser, its token would give '
            'full access to the API'
        )
    if not user.is_active or not user.is_verified:
        raise SystemExit(
            f'User {user.username} is revoked, choose another username'
        )
    # Rebinding would change what the tokens issued earlier allow
    if node_name and user.build_node_name != node_name:
        raise SystemExit(
            f'User {user.username} is bound to '
            f'{user.build_node_name or "no node (shared)"}, not {node_name}'
        )


async def issue_or_revoke(args) -> typing.Optional[str]:
    await setup_all()
    async with open_async_session(key=get_async_db_key()) as db:
        user = (
            (
                await db.execute(
                    select(User).where(User.username == args.username)
                )
            )
            .scalars()
            .first()
        )
        if args.revoke:
            if not user or not user.is_build_node:
                raise SystemExit(
                    f'No build node user {args.username} in the system'
                )
            user.is_active = False
            user.is_verified = False
            await db.flush()
            log(f'User {user.username} is revoked, its tokens are rejected')
            return
        if user:
            check_existing_user(user, args.node_name)
            log(f'Issuing one more token of user {user.username}')
        else:
            user = User(
                username=args.username,
                email=args.email or f'{args.username}@{EMAIL_DOMAIN}',
                hashed_password=None,
                is_active=True,
                is_verified=True,
                is_superuser=False,
                is_build_node=True,
                build_node_name=args.node_name,
            )
            db.add(user)
            await db.flush()
            log(f'Created build node user {user.username} ({user.email})')
        log(
            f'Bound to build node {user.build_node_name}'
            if user.build_node_name
            else 'Shared by any build nodes'
        )
        # Without lifetime_seconds the token has no exp claim
        lifetime = None
        if args.lifetime_days is not None:
            lifetime = max(1, int(args.lifetime_days * 86400))
        log(
            f'Expires in {args.lifetime_days} days'
            if lifetime
            else 'Does not expire, revoke the user to reject it'
        )
        strategy = JWTStrategy(args.secret, lifetime_seconds=lifetime)
        return await strategy.write_token(user)


def main() -> int:
    args = parse_args()
    token_output = sys.stdout
    # The server setup logs to stdout, only the token goes there
    with contextlib.redirect_stdout(sys.stderr):
        token = asyncio.run(issue_or_revoke(args))
    if token:
        print(token, file=token_output)
    return 0


if __name__ == '__main__':
    sys.exit(main())

import asyncio
import os
import sys

from fastapi_sqla import open_async_session
from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

sys.path.append(os.path.dirname(os.path.dirname(__file__)))

from alws import models
from alws.constants import (
    DEFAULT_PRODUCT,
    DEFAULT_TEAM,
    SYSTEM_USER_NAME,
)
from alws.crud.products import create_product
from alws.crud.teams import create_team
from alws.dependencies import get_async_db_key
from alws.schemas.product_schema import ProductCreate
from alws.schemas.team_schema import TeamCreate
from alws.utils.fastapi_sqla_setup import setup_all


async def ensure_system_user_exists(session: AsyncSession) -> models.User:
    user = (
        (
            await session.execute(
                select(models.User).where(
                    models.User.username == SYSTEM_USER_NAME
                )
            )
        )
        .scalars()
        .first()
    )
    if user:
        return user

    user = models.User(
        username=SYSTEM_USER_NAME,
        email=f'{SYSTEM_USER_NAME}@almalinux.org',
        is_verified=True,
        is_active=True,
    )
    session.add(user)
    await session.flush()
    return user


async def main():
    await setup_all()
    async with open_async_session(get_async_db_key()) as db:
        system_user = await ensure_system_user_exists(db)
        alma_team = await create_team(
            session=db,
            payload=TeamCreate(team_name=DEFAULT_TEAM, user_id=system_user.id),
            flush=True,
        )
        await create_product(
            db,
            ProductCreate(
                name=DEFAULT_PRODUCT,
                team_id=alma_team.id,
                owner_id=system_user.id,
                title=DEFAULT_PRODUCT,
                is_community=False,
            ),
        )


if __name__ == '__main__':
    asyncio.run(main())

import asyncio
import os
import sys

from sqlalchemy import update
from sqlalchemy.future import select
from sqlalchemy.orm import selectinload

sys.path.append(os.path.dirname(os.path.dirname(__file__)))

from alws import database, models
from alws.constants import (
    DEFAULT_PRODUCT,
    DEFAULT_TEAM,
    SYSTEM_USER_NAME,
)
from alws.crud.teams import create_team, create_team_roles
from alws.crud.products import create_product
from alws.schemas.product_schema import ProductCreate
from alws.schemas.team_schema import TeamCreate


async def ensure_system_user_exists(session: database.Session) -> models.User:
    user = (await session.execute(select(models.User).where(
        models.User.username == SYSTEM_USER_NAME))).scalars().first()
    if user:
        return user

    user = models.User(
        username=SYSTEM_USER_NAME, email=f'{SYSTEM_USER_NAME}@almalinux.org')
    session.add(user)
    await session.flush()
    await session.refresh(user)
    return user


async def main():
    db = database.Session()
    async with db.begin():
        objs = []
        system_user = await ensure_system_user_exists(db)
        alma_team = await create_team(
            db, TeamCreate(team_name=DEFAULT_TEAM, user_id=system_user.id))
        await create_product(
            db, ProductCreate(name=DEFAULT_PRODUCT, team_id=alma_team.id,
                              owner_id=system_user.id, title=DEFAULT_PRODUCT)
        )
        await db.execute(update(models.SignKey).where(
            models.SignKey.owner_id.is_(None)).values(owner_id=system_user.id))
        await db.execute(update(models.Repository).where(
            models.Repository.owner_id.is_(None)
        ).values(owner_id=system_user.id))
        await db.execute(update(models.Build).where(
            models.Build.team_id.is_(None),
        ).values(team_id=alma_team.id))
        await db.execute(update(models.Platform).where(
            models.Platform.owner_id.is_(None),
        ).values(owner_id=system_user.id))

        team_roles = await create_team_roles(db, DEFAULT_TEAM)
        existing_users = (await db.execute(
            select(models.User).options(
                selectinload(models.User.teams),
                selectinload(models.User.roles),
                selectinload(models.User.oauth_accounts)
            ))).scalars().all()
        existing_sign_keys = (await db.execute(
            select(models.SignKey).options(
                selectinload(models.SignKey.roles)
            ))).scalars().all()
        contributor_role = [r for r in team_roles
                            if 'contributor' in r.name][0]
        signer_role = [r for r in team_roles
                       if 'signer' in r.name][0]
        for user in existing_users:
            user.teams.append(alma_team)
            user.roles.append(contributor_role)
            objs.append(user)
        for sign_key in existing_sign_keys:
            sign_key.roles.append(signer_role)
            objs.append(sign_key)

        db.add_all(objs)


if __name__ == '__main__':
    asyncio.run(main())

import asyncio
import os
import sys

from sqlalchemy.future import select
from sqlalchemy.orm import selectinload

sys.path.append(os.path.dirname(os.path.dirname(__file__)))

from alws import database, models
from alws.crud.teams import create_team, create_team_roles
from alws.schemas.team_schema import TeamCreate


async def main():
    async with database.Session() as session, session.begin():
        products = (await session.execute(select(models.Product).where(
            models.Product.is_community.is_(True)).options(
                selectinload(models.Product.team).selectinload(
                    models.Team.roles),
                selectinload(models.Product.owner).selectinload(
                    models.User.roles),
        ))).scalars().all()
        add_items = []
        for product in products:
            print(f'Processing product "{product.name}"')
            team_name = f'{product.name}_team'
            if product.team.name == team_name:
                print('Product already has corresponding team')
                continue
            print('Creating a team for the product')
            team_roles = await create_team_roles(session, team_name)
            payload = TeamCreate(team_name=team_name, user_id=product.owner.id)
            team = await create_team(session, payload, flush=True)
            product.owner.roles.extend(team_roles)
            product.team = team
            add_items.extend(team_roles)
            add_items.extend([product, team, product.owner])
            print('Team is created successfully')

        session.add_all(add_items)
        await session.commit()


if __name__ == '__main__':
    asyncio.run(main())

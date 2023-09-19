import asyncio
import logging
import typing

from sqlalchemy import or_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.orm import selectinload
from sqlalchemy.sql.expression import func

from alws import models
from alws.config import settings
from alws.constants import BuildTaskStatus
from alws.crud.teams import create_team, create_team_roles, get_teams
from alws.crud.user import get_user
from alws.dramatiq import perform_product_modification
from alws.errors import DataNotFoundError, PermissionDenied, ProductError
from alws.perms import actions
from alws.perms.authorization import can_perform
from alws.schemas.product_schema import ProductCreate
from alws.schemas.team_schema import TeamCreate
from alws.utils.pulp_client import PulpClient
from alws.utils.copr import (
    create_product_repo,
    create_product_sign_key_repo,
)

__all__ = [
    'create_product',
    'get_products',
    'modify_product',
    'remove_product',
]


logger = logging.getLogger(__name__)


async def create_product(
    db: AsyncSession,
    payload: ProductCreate,
) -> models.Product:
    pulp_client = PulpClient(
        settings.pulp_host,
        settings.pulp_user,
        settings.pulp_password,
    )
    items_to_insert = []
    repo_tasks = []

    owner = await get_user(db, user_id=payload.owner_id)
    if not owner:
        raise ProductError(f'Incorrect owner ID: {payload.owner_id}')

    product = await get_products(db, product_name=payload.name)
    if product:
        raise ProductError(f'Product with name={payload.name} already exist')

    team_name = f'{payload.name}_team'
    existing_team = await get_teams(db, name=team_name)
    if existing_team:
        raise ProductError(
            "Product's team name intersects with the existing team, "
            "which may lead to permissions issues"
        )

    team_payload = TeamCreate(team_name=team_name, user_id=payload.owner_id)
    team_roles = await create_team_roles(db, team_name)
    team = await create_team(db, team_payload, flush=True)

    product_payload = payload.dict()
    product_payload['team_id'] = team.id

    product = models.Product(**product_payload)
    product.platforms = (
        (
            await db.execute(
                select(models.Platform).where(
                    models.Platform.name.in_(
                        [platform.name for platform in payload.platforms]
                    ),
                ),
            )
        )
        .scalars()
        .all()
    )

    for platform in product.platforms:
        platform_name = platform.name.lower()
        repo_tasks.extend(
            (
                create_product_repo(
                    pulp_client,
                    product.name,
                    owner.username,
                    platform_name,
                    arch,
                    is_debug,
                )
                for arch in platform.arch_list
                for is_debug in (True, False)
            )
        )
        repo_tasks.append(
            create_product_repo(
                pulp_client,
                product.name,
                owner.username,
                platform_name,
                'src',
                False,
            )
        )
    task_results = await asyncio.gather(*repo_tasks)

    for repo_name, repo_url, arch, pulp_href, is_debug in task_results:
        repo = models.Repository(
            name=repo_name,
            url=repo_url,
            arch=arch,
            pulp_href=pulp_href,
            type=arch,
            debug=is_debug,
            production=True,
        )
        product.repositories.append(repo)
        items_to_insert.append(repo)
    # Create sign key repository if a product is community
    if payload.is_community:
        repo_name, repo_url, repo_href = await create_product_sign_key_repo(
            pulp_client, owner.username, product.name)
        repo = models.Repository(
            name=repo_name,
            url=repo_url,
            arch='sign_key',
            pulp_href=repo_href,
            debug=False,
            production=True,
            type='sign_key',
        )
        product.repositories.append(repo)
        items_to_insert.append(repo)
    items_to_insert.append(product)

    owner.roles.extend(team_roles)

    db.add_all(items_to_insert)
    db.add(owner)
    await db.flush()
    await db.refresh(product)
    return product


async def get_products(
    db: AsyncSession,
    search_string: str = None,
    page_number: int = None,
    product_id: int = None,
    product_name: str = None,
) -> typing.Union[
    typing.List[models.Product],
    models.Product,
    typing.Dict[str, typing.Any],
    None,
]:
    def generate_query(count=False):
        query = (
            select(models.Product)
            .order_by(
                models.Product.id.desc(),
            )
            .options(
                selectinload(models.Product.builds),
                selectinload(models.Product.owner),
                selectinload(models.Product.platforms),
                selectinload(models.Product.repositories),
                selectinload(models.Product.roles).selectinload(
                    models.UserRole.actions
                ),
                selectinload(models.Product.team).selectinload(
                    models.Team.owner
                ),
                selectinload(models.Product.team)
                .selectinload(models.Team.roles)
                .selectinload(models.UserRole.actions),
                selectinload(models.Product.team).selectinload(
                    models.Team.members
                ),
                selectinload(models.Product.team).selectinload(
                    models.Team.products
                ),
            )
        )
        if count:
            query = select(func.count(models.Product.id))
        if search_string:
            query = query.filter(
                or_(
                    models.Product.name.like(f'%{search_string}%'),
                    models.Product.title.like(f'%{search_string}%'),
                )
            )
        if page_number and not count:
            query = query.slice(10 * page_number - 10, 10 * page_number)
        return query

    if page_number:
        return {
            'products': (await db.execute(generate_query())).scalars().all(),
            'total_products': (
                await db.execute(generate_query(count=True))
            ).scalar(),
            'current_page': page_number,
        }
    if product_id or product_name:
        query = generate_query().where(
            or_(
                models.Product.id == product_id,
                models.Product.name == product_name,
            )
        )
        return (await db.execute(query)).scalars().first()
    return (await db.execute(generate_query())).scalars().all()


async def remove_product(
    db: AsyncSession,
    product_id: int,
    user_id: int,
):
    db_product = await get_products(db, product_id=product_id)
    db_user = await get_user(db, user_id=user_id)
    if not can_perform(db_product, db_user, actions.DeleteProduct.name):
        raise PermissionDenied(
            f"User has no permissions to delete the product {db_product.name}"
        )
    if not db_product:
        raise DataNotFoundError(f"Product={product_id} doesn't exist")
    active_builds_by_team_id = (
        (
            await db.execute(
                select(models.Build.id)
                .join(models.BuildTask)
                .where(
                    models.Build.team_id == db_product.team_id,
                    models.BuildTask.status.in_(
                        [
                            BuildTaskStatus.IDLE,
                            BuildTaskStatus.STARTED,
                        ]
                    ),
                )
            )
        )
        .scalars()
        .all()
    )
    if active_builds_by_team_id:
        raise ProductError(
            f'Cannot remove product, please wait until the following '
            f'builds are finished: {str(active_builds_by_team_id)}'
        )
    pulp_client = PulpClient(
        settings.pulp_host,
        settings.pulp_user,
        settings.pulp_password,
    )
    delete_tasks = []
    all_product_distros = await pulp_client.get_rpm_distros(
        include_fields=["pulp_href"],
        **{"name__startswith": db_product.pulp_base_distro_name},
    )
    for product_repo in db_product.repositories:
        delete_tasks.append(pulp_client.delete_by_href(product_repo.pulp_href))
    for product_distro in all_product_distros:
        delete_tasks.append(
            pulp_client.delete_by_href(product_distro["pulp_href"]),
        )
    await asyncio.gather(*delete_tasks)
    await db.delete(db_product)
    await db.commit()


async def modify_product(
    db: AsyncSession,
    build_id: int,
    product: str,
    user_id: int,
    modification: str,
):
    async with db.begin():
        db_product = await get_products(db, product_name=product)
        db_user = await get_user(db, user_id=user_id)
        if not db_user:
            raise DataNotFoundError(f"User={user_id} doesn't exist")
        if not can_perform(db_product, db_user, actions.ReleaseToProduct.name):
            raise PermissionDenied(
                f'User has no permissions '
                f'to modify the product "{db_product.name}"'
            )

        db_build = await db.execute(
            select(models.Build)
            .where(
                models.Build.id == build_id,
            )
            .options(
                selectinload(models.Build.repos),
                selectinload(models.Build.tasks).selectinload(
                    models.BuildTask.rpm_module
                ),
                selectinload(models.Build.tasks).selectinload(
                    models.BuildTask.platform
                ),
            ),
        )
        db_build = db_build.scalars().first()

        if modification == 'add':
            if db_build in db_product.builds:
                error_msg = (
                    f"Can't add build {build_id} to {product} "
                    f"as it's already part of the product"
                )
                raise ProductError(error_msg)
        if modification == 'remove':
            if db_build not in db_product.builds:
                error_msg = (
                    f"Can't remove build {build_id} "
                    f"from {product} as it's not part "
                    f"of the product"
                )
                raise ProductError(error_msg)

    perform_product_modification.send(db_build.id, db_product.id, modification)

import asyncio
import logging
import pprint
import typing
from collections import defaultdict

from sqlalchemy import or_
from sqlalchemy.future import select
from sqlalchemy.orm import selectinload
from sqlalchemy.sql.expression import func

from alws import models
from alws.config import settings
from alws.constants import BuildTaskStatus
from alws.crud.user import get_user
from alws.crud.teams import (
    create_team,
    create_team_roles,
    get_teams,
)
from alws.database import Session
from alws.errors import ProductError, PermissionDenied
from alws.perms import actions
from alws.perms.authorization import can_perform
from alws.schemas.product_schema import ProductCreate
from alws.schemas.team_schema import TeamCreate
from alws.utils.pulp_client import PulpClient
from alws.utils.copr import create_product_repo

__all__ = [
    'create_product',
    'get_products',
    'modify_product',
    'remove_product',
]


logger = logging.getLogger(__name__)


async def create_product(
    db: Session,
    payload: ProductCreate,
) -> models.Product:

    pulp_client = PulpClient(settings.pulp_host, settings.pulp_user,
                             settings.pulp_password)
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
            f"Product's team name intersects with the existing team, "
            f"which may lead to permissions issues")

    team_payload = TeamCreate(team_name=team_name, user_id=payload.owner_id)
    team_roles = await create_team_roles(db, team_name)
    team = await create_team(db, team_payload, flush=True)

    product_payload = payload.dict()
    product_payload['team_id'] = team.id

    product = models.Product(**product_payload)
    product.platforms = (await db.execute(
        select(models.Platform).where(
            models.Platform.name.in_([
                platform.name
                for platform in payload.platforms
            ]),
        ),
    )).scalars().all()

    for platform in product.platforms:
        platform_name = platform.name.lower()
        repo_tasks.extend((
            create_product_repo(pulp_client, product.name, owner.username,
                                platform_name, arch, is_debug)
            for arch in platform.arch_list
            for is_debug in (True, False)
        ))
        repo_tasks.append(create_product_repo(
            pulp_client, product.name, owner.username,
            platform_name, 'src', False))
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
    items_to_insert.append(product)

    owner.roles.extend(team_roles)

    db.add_all(items_to_insert)
    db.add(owner)
    await db.flush()
    await db.refresh(product)
    return product


async def get_products(
    db: Session,
    search_string: str = None,
    page_number: int = None,
    product_id: int = None,
    product_name: str = None,
) -> typing.Union[
    typing.List[models.Product],
    models.Product,
]:

    def generate_query(count=False):
        query = select(models.Product).order_by(
            models.Product.id.desc(),
        ).options(
            selectinload(models.Product.builds),
            selectinload(models.Product.owner),
            selectinload(models.Product.platforms),
            selectinload(models.Product.repositories),
            selectinload(models.Product.roles).selectinload(
                models.UserRole.actions),
            selectinload(models.Product.team).selectinload(
                models.Team.owner),
            selectinload(models.Product.team).selectinload(
                models.Team.roles).selectinload(models.UserRole.actions),
            selectinload(models.Product.team).selectinload(
                models.Team.members),
            selectinload(models.Product.team).selectinload(
                models.Team.products),
        )
        if count:
            query = select(func.count(models.Product.id))
        if search_string:
            query = query.filter(or_(
                models.Product.name.like(f'%{search_string}%'),
                models.Product.title.like(f'%{search_string}%'),
            ))
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
        query = generate_query().where(or_(
            models.Product.id == product_id,
            models.Product.name == product_name,
        ))
        return (await db.execute(query)).scalars().first()
    return (await db.execute(generate_query())).scalars().all()


async def remove_product(
    db: Session,
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
        raise Exception(f"Product={product_id} doesn't exist")
    pulp_client = PulpClient(settings.pulp_host, settings.pulp_user,
                             settings.pulp_password)
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


async def get_existing_packages(
    pulp_client: PulpClient,
    repository: models.Repository,
) -> typing.List[typing.Dict[str, str]]:

    pulp_fields = ['pulp_href', 'artifact', 'sha256', 'location_href', 'arch']
    return await pulp_client.get_rpm_repository_packages(
        repository.pulp_href,
        include_fields=pulp_fields,
    )


async def get_packages(
    pulp_client: PulpClient,
    build_repo: models.Repository,
    dist_repo: models.Repository,
    modification: str
) -> typing.Tuple[str, typing.List[str]]:

    def filter_by_arch(pkgs: typing.List[dict], repo_arch: str):
        filtered = []
        for pkg in pkgs:
            if pkg['arch'] == 'noarch' and repo_arch != 'src':
                filtered.append(pkg)
            elif pkg['arch'] == 'i686' and repo_arch in ('i686', 'x86_64'):
                filtered.append(pkg)
            elif pkg['arch'] == repo_arch:
                filtered.append(pkg)
        return filtered

    dist_packages = await get_existing_packages(pulp_client, dist_repo)
    search_by_href = set([pkg['pulp_href'] for pkg in dist_packages])
    build_packages = await get_existing_packages(pulp_client, build_repo)
    filtered_build_packages = filter_by_arch(build_packages, dist_repo.arch)
    logger.debug('Packages in product repository %s:\n%s', dist_repo.name,
                 pprint.pformat(dist_packages))
    logger.debug('Set of packages HREFs for comparison '
                 'with build artifacts:\n%s',
                 pprint.pformat(search_by_href))
    logger.debug('List of build packages in build repository %s:\n%s',
                 build_repo.name, pprint.pformat(filtered_build_packages))
    if modification == 'add':
        dedup_mapping = {}
        for pkg in filtered_build_packages:
            if pkg['location_href'] in dedup_mapping:
                continue
            dedup_mapping[pkg['location_href']] = pkg['pulp_href']
        logger.debug('Deduplication mapping for packages'
                     'with the same name:\n%s', pprint.pformat(dedup_mapping))
        final_packages = [href for href in dedup_mapping.values()
                          if href not in search_by_href]
    else:
        final_packages = [pkg['pulp_href'] for pkg in filtered_build_packages
                          if pkg['pulp_href'] in search_by_href]
    logger.debug('Final list of packages to %s:\n%s', modification,
                 pprint.pformat(final_packages))
    return dist_repo.pulp_href, final_packages


async def prepare_repo_modify_dict(
    db_build: models.Build,
    db_product: models.Product,
    pulp_client: PulpClient,
    modification: str
) -> typing.Dict[str, typing.List[str]]:

    product_repo_mapping = {(repo.arch, repo.debug, repo.platform.name): repo
                            for repo in db_product.repositories}
    modify = defaultdict(list)
    build_repos = [repo for repo in db_build.repos if repo.type == 'rpm']
    tasks = []
    for repo in build_repos:
        dist_repo = product_repo_mapping.get(
            (repo.arch, repo.debug, repo.platform.name)
        )
        if dist_repo is None:
            continue
        tasks.append(get_packages(pulp_client, repo, dist_repo, modification))

    results = await asyncio.gather(*tasks)
    modify.update(**dict(results))

    for task in db_build.tasks:
        if task.status != BuildTaskStatus.COMPLETED:
            continue
        if task.rpm_module:
            product_repo = product_repo_mapping.get(
                (task.arch, False, task.platform.name)
            )
            if product_repo is None:
                continue
            modify[product_repo.pulp_href].append(task.rpm_module.pulp_href)

    return modify


async def set_platform_for_products_repos(
        db: Session,
        product: models.Product,
) -> None:
    repo_debug_dict = {
        True: 'debug-dr',
        False: '-dr',
    }
    # name of a product's repo:
    # some-username-some-product-some-platform-x86_64-debug-dr
    repos_per_platform = {
        f"{platform.owner.username}-{product.name}-{platform.name}-"
        f"{repo.type}-{repo_debug_dict[repo.debug]}": platform
        for repo in product.repositories for platform in product.platforms
    }
    # we do nothing if all repos have platform
    if all(repo.platform for repo in product.repositories):
        return
    for repo in product.repositories:
        repo.platform = repos_per_platform[repo.name]
    db.add(product)
    try:
        await db.commit()
        await db.refresh(product)
    except Exception:
        await db.rollback()


async def set_platform_for_build_repos(
        db: Session,
        build: models.Build,
) -> None:
    repo_debug_dict = {
        True: 'debug-br',
        False: '-br',
    }
    # name of a build's repo:
    # some-platform-x86_64-some-build-id-debug-br
    repos_per_platform = {
        f"{task.platform.name}-{repo.arch}-{build.id}-"
        f"{repo_debug_dict[repo.debug]}": task.platform
        for repo in build.repos for task in build.tasks
    }
    # we do nothing if all repos have platform
    if all(repo.platform for repo in build.repos):
        return
    for repo in build.repos:
        repo.platform = repos_per_platform[repo.name]
    db.add(build)
    try:
        await db.commit()
        await db.refresh(build)
    except Exception:
        await db.rollback()


async def modify_product(
    db: Session,
    build_id: int,
    product: str,
    user_id: int,
    modification: str,
    force: bool = False,
):

    async with db.begin():
        db_product = await get_products(db, product_name=product)
        db_user = await get_user(db, user_id=user_id)
        if not db_user:
            raise
        if not can_perform(db_product, db_user, actions.ReleaseToProduct.name):
            raise PermissionDenied(
                f'User has no permissions '
                f'to modify the product "{db_product.name}"'
            )

        db_build = await db.execute(
            select(models.Build).where(
                models.Build.id.__eq__(build_id),
            ).options(
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

        if modification == 'add' and not force:
            if db_build in db_product.builds:
                error_msg = f'Packages of build {build_id} have already been' \
                            f' added to {product} product'
                raise ProductError(error_msg)
        if modification == 'remove' and not force:
            if db_build not in db_product.builds:
                error_msg = f'Packages of build {build_id} cannot ' \
                            f'be from {product} product ' \
                            f'as they are not added there'
                raise ProductError(error_msg)

    pulp_client = PulpClient(settings.pulp_host, settings.pulp_user,
                             settings.pulp_password)
    await set_platform_for_products_repos(db=db, product=db_product)
    await set_platform_for_build_repos(db=db, build=db_build)
    modify = await prepare_repo_modify_dict(
        db_build, db_product, pulp_client, modification)
    tasks = []
    publish_tasks = []
    for key, value in modify.items():
        if modification == 'add':
            tasks.append(pulp_client.modify_repository(add=value, repo_to=key))
        else:
            tasks.append(pulp_client.modify_repository(
                remove=value, repo_to=key))
        # We've changed products repositories to not invoke
        # automatic publications, so now we need
        # to manually publish them after modification
        publish_tasks.append(pulp_client.create_rpm_publication(key))
    await asyncio.gather(*tasks)
    await asyncio.gather(*publish_tasks)

    if modification == 'add':
        db_product.builds.append(db_build)
    else:
        db_product.builds.remove(db_build)
    db.add(db_product)
    try:
        await db.commit()
    except Exception:
        await db.rollback()

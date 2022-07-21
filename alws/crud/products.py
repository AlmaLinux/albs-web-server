import asyncio
from collections import defaultdict
import typing

from sqlalchemy import delete, or_
from sqlalchemy.future import select
from sqlalchemy.orm import selectinload
from sqlalchemy.sql.expression import func

from alws import models
from alws.config import settings
from alws.constants import BuildTaskStatus
from alws.database import Session
from alws.errors import ProductError
from alws.schemas.product_schema import ProductCreate
from alws.utils.pulp_client import PulpClient


__all__ = [
    'create_product',
    'get_products',
]


async def create_product_repo(
    pulp_client: PulpClient,
    product_name: str,
    platform_name: str,
    arch: str,
    is_debug: bool,
) -> typing.Tuple[str, str, str, str, bool]:

    debug_suffix = '-debug' if is_debug else ''
    repo_name = f'{product_name}-{platform_name}-{arch}{debug_suffix}-dr'
    repo_url, repo_href = await pulp_client.create_build_rpm_repo(repo_name)
    return repo_name, repo_url, arch, repo_href, is_debug


async def create_product(
    db: Session,
    payload: ProductCreate,
) -> models.Product:

    pulp_client = PulpClient(settings.pulp_host, settings.pulp_user,
                             settings.pulp_password)
    items_to_insert = []
    repo_tasks = []
    test_team_id = (await db.execute(select(models.Team.id).where(
        models.Team.id == payload.team_id))).scalars().first()
    if not test_team_id:
        raise ValueError(f'Incorrect team ID: {payload.team_id}')

    test_owner_id = (await db.execute(select(models.User.id).where(
        models.User.id == payload.owner_id))).scalars().first()
    if not test_owner_id:
        raise ValueError(f'Incorrect owner ID: {payload.owner_id}')

    product = (await db.execute(select(models.Product).where(
        models.Product.name == payload.name))).scalars().first()
    if product:
        return product

    product = models.Product(**payload.dict())
    product.platforms = (await db.execute(
        select(models.Platform).where(
            models.Platform.name.in_([
                platform.name
                for platform in payload.platforms
            ]),
        ),
    )).scalars().all()
    items_to_insert.append(product)
    for platform in product.platforms:
        platform_name = platform.name
        repo_tasks.extend((
            create_product_repo(pulp_client, product.name,
                                platform_name, arch, is_debug)
            for arch in platform.arch_list
            for is_debug in (True, False)
        ))
        repo_tasks.append(create_product_repo(
            pulp_client, product.name, platform_name, 'src', False))
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

    db.add_all(items_to_insert)
    await db.flush()
    await db.refresh(product)
    return product


async def get_products(
    db: Session,
    search_string: str = None,
    page_number: int = None,
    product_id: int = None,
) -> typing.Union[
    typing.List[models.Product],
    models.Product,
]:

    query = select(models.Product).order_by(
        models.Product.id.desc(),
    ).options(
        selectinload(models.Product.builds),
        selectinload(models.Product.owner),
        selectinload(models.Product.platforms),
        selectinload(models.Product.repositories),
        selectinload(models.Product.team).selectinload(models.Team.members),
        selectinload(models.Product.team).selectinload(models.Team.owner),
        selectinload(models.Product.team).selectinload(models.Team.roles),
    )
    if search_string:
        query = query.filter(or_(
            models.Product.name.like(f'%{search_string}%'),
            models.Product.title.like(f'%{search_string}%'),
        ))
    if page_number:
        query = query.slice(10 * page_number - 10, 10 * page_number)
        return {
            'products': (await db.execute(query)).scalars().all(),
            'total_products': (
                await db.execute(select(func.count(models.Product.id)))
            ).scalar(),
            'current_page': page_number,
        }
    if product_id:
        query = query.where(models.Product.id == product_id)
        return (await db.execute(query)).scalars().first()
    return (await db.execute(query)).scalars().all()


async def remove_product(
    db: Session,
    product_id: int,
):

    db_product = (await db.execute(
        select(models.Product).where(
            models.Product.id == product_id,
        ).options(
            selectinload(models.Product.repositories),
        ),
    )).scalars().first()
    if not db_product:
        raise Exception(f"Product={product_id} doesn't exist")
    pulp_client = PulpClient(settings.pulp_host, settings.pulp_user,
                             settings.pulp_password)
    await asyncio.gather(*(
        pulp_client.delete_by_href(product_repo.pulp_href)
        for product_repo in db_product.repositories
    ))
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


async def get_packages_to_add(
    pulp_client: PulpClient,
    build_repo: models.Repository,
    dist_repo: models.Repository,
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
    dedup_mapping = {pkg['location_href']: pkg['pulp_href']
                     for pkg in filtered_build_packages}
    final_packages = [href for href in dedup_mapping.values()
                      if href not in search_by_href]
    return dist_repo.pulp_href, final_packages


async def prepare_repo_modify_dict(
    db_build: models.Build,
    db_product: models.Product,
    pulp_client: PulpClient,
) -> typing.Dict[str, typing.List[str]]:

    product_repo_mapping = {(repo.arch, repo.debug): repo
                            for repo in db_product.repositories}
    modify = defaultdict(list)
    build_repos = [repo for repo in db_build.repos if repo.type == 'rpm']
    tasks = []
    for repo in build_repos:
        dist_repo = product_repo_mapping.get((repo.arch, repo.debug))
        tasks.append(get_packages_to_add(pulp_client, repo, dist_repo))

    results = await asyncio.gather(*tasks)
    modify.update(**dict(results))

    for task in db_build.tasks:
        if task.status != BuildTaskStatus.COMPLETED:
            continue
        if task.rpm_module:
            product_repo = product_repo_mapping.get((task.arch, False))
            modify[product_repo.pulp_href].append(task.rpm_module.pulp_href)

    return modify


async def modify_product(
    db: Session,
    build_id: int,
    product: str,
    modification: str,
    force: bool = False,
):

    async with db.begin():
        db_product = await db.execute(
            select(models.Product).where(
                models.Product.name.__eq__(product),
            ).options(
                selectinload(models.Product.repositories),
                selectinload(models.Product.builds),
            ),
        )
        db_product = db_product.scalars().first()

        db_build = await db.execute(
            select(models.Build).where(
                models.Build.id.__eq__(build_id),
            ).options(
                selectinload(models.Build.repos),
                selectinload(models.Build.tasks).selectinload(
                    models.BuildTask.rpm_module),
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
                error_msg = f'Packages of build {build_id} cannot be removed ' \
                            f'from {product} product ' \
                            f'as they are not added there'
                raise ProductError(error_msg)

    pulp_client = PulpClient(settings.pulp_host, settings.pulp_user,
                             settings.pulp_password)
    modify = await prepare_repo_modify_dict(db_build, db_product, pulp_client)
    tasks = []
    for key, value in modify.items():
        if modification == 'add':
            tasks.append(pulp_client.modify_repository(add=value, repo_to=key))
        else:
            tasks.append(pulp_client.modify_repository(
                remove=value, repo_to=key))
    await asyncio.gather(*tasks)

    if modification == 'add':
        db_product.builds.append(db_build)
    else:
        remove_query = models.Build.id.__eq__(build_id)
        await db.execute(
            delete(models.ProductBuilds).where(remove_query)
        )
    db.add(db_product)
    try:
        await db.commit()
    except Exception:
        await db.rollback()

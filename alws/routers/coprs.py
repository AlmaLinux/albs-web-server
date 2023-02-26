import typing

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import PlainTextResponse
from fastapi_sqla.asyncio_support import AsyncSession
from sqlalchemy import select, and_
from sqlalchemy.orm import selectinload

from alws import models
from alws.utils.copr import (
    generate_repo_config,
    get_clean_copr_chroot,
    make_copr_plugin_response,
)

copr_router = APIRouter(
    tags=['coprs'],
)


@copr_router.get('/api_3/project/search')
async def search_repos(
    query: str,
    db: AsyncSession = Depends(),
) -> typing.Dict:
    query = select(models.Product).where(
        models.Product.name == query,
    ).options(
        selectinload(models.Product.repositories),
        selectinload(models.Product.owner),
    )
    db_products = (await db.execute(query)).scalars().all()
    return {'items': make_copr_plugin_response(db_products)}


@copr_router.get('/api_3/project/list')
async def list_repos(
    ownername: str,
    db: AsyncSession = Depends(),
) -> typing.Dict:
    query = select(models.Product).where(
        models.Product.owner.has(username=ownername),
    ).options(
        selectinload(models.Product.repositories),
        selectinload(models.Product.owner),
    )
    db_products = (await db.execute(query)).scalars().all()
    return {'items': make_copr_plugin_response(db_products)}


@copr_router.get(
    '/coprs/{ownername}/{name}/repo/{platform}/dnf.repo',
    response_class=PlainTextResponse,
)
async def get_dnf_repo_config(
    ownername: str,
    name: str,
    platform: str,
    arch: str,
    db: AsyncSession = Depends(),
):
    chroot = f'{platform}-{arch}'
    clean_chroot = get_clean_copr_chroot(chroot)
    db_product = await db.execute(
        select(models.Product).where(and_(
            models.Product.name == name,
            models.Product.owner.has(username=ownername),
        )).options(
            selectinload(models.Product.repositories),
            selectinload(models.Product.owner),
        ),
    )
    db_product = db_product.scalars().first()
    if not db_product:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f'Product {name} for user {ownername} is not found'
        )
    for product_repo in db_product.repositories:
        if product_repo.debug or arch != product_repo.arch:
            continue
        if product_repo.name.lower().endswith(clean_chroot):
            return generate_repo_config(
                product_repo, db_product.name, ownername)
    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail=f"Didn't find matching repositories in {name} for chroot {chroot}"
    )

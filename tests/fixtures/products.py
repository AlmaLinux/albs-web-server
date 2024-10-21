from typing import AsyncIterable

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from alws.crud.products import create_product
from alws.crud.sign_task import create_gen_key_task
from alws.crud.user import get_user
from alws.models import Product, Repository
from alws.schemas.product_schema import ProductCreate
from tests.constants import ADMIN_USER_ID


@pytest.fixture(
    params=[
        ADMIN_USER_ID,
    ]
)
def product_create_payload(request) -> dict:
    return {
        "name": "AlmaLinux",
        "owner_id": request.param,
        "title": "AlmaLinux",
        "description": "",
        "platforms": [
            {
                "id": 1,
                "name": "AlmaLinux-8",
                "distr_type": "rhel",
                "distr_version": "8",
                "arch_list": [
                    "i686",
                    "x86_64",
                    "ppc64le",
                    "aarch64",
                    "s390x",
                ],
                "modularity": {},
            },
        ],
        "is_community": False,
    }


@pytest.fixture
def add_platfroms_to_product_payload() -> list:
    return [
        {
            "id": 1,
            "name": "AlmaLinux-9",
            "distr_type": "rhel",
            "distr_version": "9",
            "arch_list": [
                "i686",
                "x86_64",
                "ppc64le",
                "aarch64",
                "s390x",
            ],
            "modularity": {},
        }
    ]


@pytest.fixture(
    params=[
        ADMIN_USER_ID,
    ]
)
def user_product_create_payload(request) -> dict:
    return {
        "name": "testy-testy",
        "owner_id": request.param,
        "title": "Testy's Product",
        "description": "",
        "platforms": [
            {
                "id": 1,
                "name": "AlmaLinux-8",
                "distr_type": "rhel",
                "distr_version": "8",
                "arch_list": [
                    "i686",
                    "x86_64",
                    "ppc64le",
                    "aarch64",
                    "s390x",
                ],
                "modularity": {},
            },
        ],
        "is_community": True,
    }


@pytest.fixture
async def base_product(
    async_session: AsyncSession, product_create_payload: dict, create_repo
) -> AsyncIterable[Product]:
    product = (
        (
            await async_session.execute(
                select(Product).where(
                    Product.name == product_create_payload["name"],
                ),
            )
        )
        .scalars()
        .first()
    )
    if not product:
        product = await create_product(
            async_session,
            ProductCreate(**product_create_payload),
        )
    await async_session.commit()
    yield product


@pytest.fixture
async def product_with_repo(
    async_session: AsyncSession,
    base_product: Product,
    repository_for_product: Repository,
    base_platform,
):
    product = (
        (
            await async_session.execute(
                select(Product)
                .where(
                    Product.name == base_product.name,
                )
                .options(selectinload(Product.repositories))
            )
        )
        .scalars()
        .first()
    )
    product.repositories.append(repository_for_product)
    async_session.add(product)
    await async_session.commit()
    yield product


@pytest.fixture
async def user_product(
    async_session: AsyncSession,
    user_product_create_payload: dict,
    create_repo,
    create_file_repository,
) -> AsyncIterable[Product]:
    product = (
        (
            await async_session.execute(
                select(Product).where(
                    Product.name == user_product_create_payload["name"],
                ),
            )
        )
        .scalars()
        .first()
    )
    if not product:
        product = await create_product(
            async_session,
            ProductCreate(**user_product_create_payload),
        )
        await create_gen_key_task(
            async_session,
            product,
            await get_user(async_session, user_id=user_product_create_payload['owner_id']),
        )
        await async_session.commit()
    yield product

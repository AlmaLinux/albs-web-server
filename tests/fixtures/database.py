import pytest

from fastapi_sqla import Base
from sqlalchemy import insert, select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.pool import NullPool

from alws import models
from alws.config import settings

from tests.constants import ADMIN_USER_ID

engine = create_async_engine(
    settings.test_database_url,
    poolclass=NullPool,
    echo_pool=True,
)


@pytest.mark.anyio
@pytest.fixture(scope="session", autouse=True)
async def create_tables():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


@pytest.mark.anyio
@pytest.fixture(
    autouse=True,
    params=[
        {
            "id": ADMIN_USER_ID,
            "username": "admin",
            "email": "admin@almalinux.com",
            "is_superuser": True,
            "is_verified": True,
        },
    ],
)
async def create_user(async_session: AsyncSession, request):
    data = {
        "id": request.param["id"],
        "username": request.param["username"],
        "email": request.param["email"],
        "is_superuser": request.param["is_superuser"],
        "is_verified": request.param["is_verified"],
    }
    user = await (
        async_session.execute(
            select(models.User).where(models.User.id == data["id"]),
        )
    )
    if user.scalars().first():
        return
    await async_session.execute(insert(models.User).values(**data))
    await async_session.commit()

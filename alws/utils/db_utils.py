from fastapi_sqla import asyncio_support

from alws import models
from alws.database import engine


__all__ = ['prepare_mappings']


async def prepare_mappings():
    """
    Properly maps models to the current database connection
    for separate scripts execution
    """
    models.Base.metadata.bind = engine
    asyncio_support._AsyncSession.configure(
        bind=engine, expire_on_commit=False)
    async with engine.begin() as conn:
        await conn.run_sync(models.Base.prepare)

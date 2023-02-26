from functools import wraps

from fastapi_sqla import asyncio_support, sqla

from alws import models
from alws.database import engine, sync_engine


__all__ = ['prepare_mappings']


ARE_MAPPINGS_DONE = False


def prepare_mappings(func):

    @wraps(func)
    async def decorator(*args, **kwargs):
        global ARE_MAPPINGS_DONE
        if ARE_MAPPINGS_DONE:
            return

        models.Base.metadata.bind = engine
        asyncio_support._AsyncSession.configure(
            bind=engine, expire_on_commit=False)
        sqla._Session.configure(bind=sync_engine, expire_on_commit=False)

        async with engine.begin() as conn:
            await conn.run_sync(models.Base.prepare)

        with sync_engine.begin() as conn:
            conn.run_callable(models.Base.prepare)
        result = await func(*args, **kwargs)
        return result

    return decorator

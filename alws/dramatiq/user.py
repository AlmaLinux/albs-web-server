import dramatiq
from fastapi_sqla import open_async_session
from sqlalchemy import delete
from sqlalchemy.future import select

from alws import models
from alws.constants import DRAMATIQ_TASK_TIMEOUT
from alws.crud import build as build_crud
from alws.dependencies import get_async_db_key
from alws.dramatiq import event_loop
from alws.utils.fastapi_sqla_setup import setup_all

__all__ = ['perform_user_removal']


async def _perform_user_removal(user_id: int):
    async with open_async_session(key=get_async_db_key()) as db:
        # Remove builds
        build_ids = (
            (
                await db.execute(
                    select(models.Build.id).where(
                        models.Build.owner_id == user_id
                    )
                )
            )
            .scalars()
            .all()
        )
        await db.flush()

        for build_id in build_ids:
            await build_crud.remove_build_job(db, build_id)

        await db.execute(delete(models.User).where(models.User.id == user_id))


@dramatiq.actor(max_retries=0, priority=0, time_limit=DRAMATIQ_TASK_TIMEOUT)
def perform_user_removal(user_id: int):
    event_loop.run_until_complete(setup_all())
    event_loop.run_until_complete(_perform_user_removal(user_id))

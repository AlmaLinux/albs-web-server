import dramatiq

from fastapi_sqla.asyncio_support import open_session
from sqlalchemy import delete
from sqlalchemy.future import select

from alws import models
from alws.constants import DRAMATIQ_TASK_TIMEOUT
from alws.crud import build as build_crud
from alws.dramatiq import event_loop
from alws.utils.db_utils import prepare_mappings

__all__ = ['perform_user_removal'] 


@prepare_mappings
async def _perform_user_removal(user_id: int):
    async with open_session() as db:
        async with db.begin():
            # Remove builds
            build_ids = (await db.execute(
                select(models.Build.id).where(
                  models.Build.owner_id == user_id
                )
            )).scalars().all()

        for build_id in build_ids:
            await build_crud.remove_build_job(db, build_id)

        async with db.begin():
            await db.execute(delete(models.User).where(
                models.User.id == user_id))


@dramatiq.actor(max_retries=0, priority=0, time_limit=DRAMATIQ_TASK_TIMEOUT)
def perform_user_removal(user_id: int):
    event_loop.run_until_complete(_perform_user_removal(user_id))

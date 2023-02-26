import dramatiq
from fastapi_sqla.asyncio_support import open_session

from alws.constants import DRAMATIQ_TASK_TIMEOUT
from alws.crud import release as r_crud
from alws.dramatiq import event_loop
from alws.utils.db_utils import prepare_mappings


__all__ = ["execute_release_plan"]


@prepare_mappings
async def _commit_release(release_id, user_id):
    async with open_session() as db:
        await r_crud.commit_release(db, release_id, user_id)


@dramatiq.actor(
    max_retries=0,
    priority=0,
    queue_name='releases',
    time_limit=DRAMATIQ_TASK_TIMEOUT,
)
def execute_release_plan(release_id: int, user_id: int):
    event_loop.run_until_complete(_commit_release(release_id, user_id))

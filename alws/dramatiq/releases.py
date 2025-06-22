import dramatiq
from fastapi_sqla import open_async_session

from alws.constants import DRAMATIQ_TASK_TIMEOUT
from alws.crud import release as r_crud
from alws.dependencies import get_async_db_key
from alws.dramatiq import event_loop
from alws.utils.fastapi_sqla_setup import setup_all
from alws.utils.sentry import sentry_init

__all__ = ["execute_release_plan"]


sentry_init()


async def _commit_release(release_id, user_id):
    async with open_async_session(key=get_async_db_key()) as db:
        await r_crud.commit_release(db, release_id, user_id)


async def _revert_release(release_id, user_id):
    async with open_async_session(key=get_async_db_key()) as db:
        await r_crud.revert_release(db, release_id, user_id)


@dramatiq.actor(
    max_retries=0,
    priority=0,
    queue_name="releases",
    time_limit=DRAMATIQ_TASK_TIMEOUT,
)
def execute_release_plan(release_id: int, user_id: int):
    event_loop.run_until_complete(setup_all())
    event_loop.run_until_complete(_commit_release(release_id, user_id))


@dramatiq.actor(
    max_retries=0,
    priority=0,
    queue_name="releases",
    time_limit=DRAMATIQ_TASK_TIMEOUT,
)
def revert_release(release_id: int, user_id: int):
    event_loop.run_until_complete(setup_all())
    event_loop.run_until_complete(_revert_release(release_id, user_id))

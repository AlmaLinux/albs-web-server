from contextlib import asynccontextmanager

import dramatiq

from alws.constants import DRAMATIQ_TASK_TIMEOUT
from alws.crud import release as r_crud
from alws.dramatiq import event_loop
from alws.dependencies import get_db

__all__ = ["execute_release_plan"]


async def _commit_release(release_id, user_id):
    async with asynccontextmanager(get_db)() as db:
        await r_crud.commit_release(db, release_id, user_id)


async def _revert_release(release_id, user_id):
    async with asynccontextmanager(get_db)() as db:
        await r_crud.revert_release(db, release_id, user_id)


@dramatiq.actor(
    max_retries=0,
    priority=0,
    queue_name="releases",
    time_limit=DRAMATIQ_TASK_TIMEOUT,
)
def execute_release_plan(release_id: int, user_id: int):
    event_loop.run_until_complete(_commit_release(release_id, user_id))


@dramatiq.actor(
    max_retries=0,
    priority=0,
    queue_name="releases",
    time_limit=DRAMATIQ_TASK_TIMEOUT,
)
def revert_release(release_id: int, user_id: int):
    event_loop.run_until_complete(_revert_release(release_id, user_id))

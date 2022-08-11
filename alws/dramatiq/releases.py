import dramatiq

from fastapi_sqla import open_async_session

from alws.constants import DRAMATIQ_TASK_TIMEOUT
from alws.dramatiq import event_loop
from alws.dependencies import get_pulp_db
from alws.release_planner import ReleasePlanner

__all__ = ["execute_release_plan"]


async def _commit_release(release_id, user_id):
    async with open_async_session() as db:
        for pulp_db in get_pulp_db():
            release_planner = ReleasePlanner(db, pulp_db)
            await release_planner.commit_release(release_id, user_id)


@dramatiq.actor(
    max_retries=0,
    priority=0,
    time_limit=DRAMATIQ_TASK_TIMEOUT,
)
def execute_release_plan(release_id: int, user_id: int):
    event_loop.run_until_complete(_commit_release(release_id, user_id))

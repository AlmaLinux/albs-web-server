import typing

import dramatiq

from alws.crud import sign_task
from alws.dependencies import get_db
from alws.dramatiq import event_loop
from alws.schemas import sign_schema


__all__ = ['complete_sign_task']


async def _complete_sign_task(
        task_id: int, payload: typing.Dict[str, typing.Any]):
    async for db in get_db():
        await sign_task.complete_sign_task(
            db, task_id, sign_schema.SignTaskComplete(**payload))


@dramatiq.actor(max_retries=2, priority=1, time_limit=3600000)
def complete_sign_task(task_id: int, payload: typing.Dict[str, typing.Any]):
    event_loop.run_until_complete(_complete_sign_task(task_id, payload))

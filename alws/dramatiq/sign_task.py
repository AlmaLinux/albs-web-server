import typing

import dramatiq
from alws.constants import DRAMATIQ_TASK_TIMEOUT
from alws.crud import sign_task
from alws.dramatiq import event_loop
from alws.schemas import sign_schema
from alws.utils.fastapi_sqla_setup import setup_all
from alws.utils.sentry import sentry_init

__all__ = ['complete_sign_task']


sentry_init()


async def _complete_sign_task(
    task_id: int, payload: typing.Dict[str, typing.Any]
):
    await sign_task.complete_sign_task(
        task_id, sign_schema.SignTaskComplete(**payload)
    )


# Timeout for the task is set to 1 hour in milliseconds. This is needed
# to process large jobs with a lot of RPM packages inside
@dramatiq.actor(
    max_retries=2,
    priority=1,
    queue_name='sign',
    time_limit=DRAMATIQ_TASK_TIMEOUT,
)
def complete_sign_task(task_id: int, payload: typing.Dict[str, typing.Any]):
    event_loop.run_until_complete(setup_all())
    event_loop.run_until_complete(_complete_sign_task(task_id, payload))

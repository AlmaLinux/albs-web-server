import logging
import typing

import dramatiq
from fastapi_sqla import open_async_session

from alws.constants import DRAMATIQ_TASK_TIMEOUT, TestTaskStatus
from alws.crud import test as t_crud
from alws.dependencies import get_async_db_key
from alws.dramatiq._event_loop import event_loop
from alws.schemas.test_schema import TestTaskResult
from alws.utils.fastapi_sqla_setup import setup_all

__all__ = ['complete_test_task']


async def _complete_test_task(task_id: int, task_result: TestTaskResult):
    async with open_async_session(key=get_async_db_key()) as db:
        try:
            logging.info('Start processing test task %s', task_id)
            await t_crud.complete_test_task(db, task_id, task_result)
            logging.info('Processing test task %s is finished', task_id)
        except Exception as e:
            logging.exception(
                'Cannot set test task "%d" result, marking as failed.'
                'Error: %s',
                task_id,
                str(e),
            )
            await t_crud.update_test_task(
                db, task_id, task_result, status=TestTaskStatus.FAILED
            )
            raise e


@dramatiq.actor(
    max_retries=0,
    priority=0,
    queue_name='tests',
    time_limit=DRAMATIQ_TASK_TIMEOUT,
)
def complete_test_task(task_id: int, payload: typing.Dict[str, typing.Any]):
    event_loop.run_until_complete(setup_all())
    event_loop.run_until_complete(
        _complete_test_task(task_id, TestTaskResult(**payload))
    )

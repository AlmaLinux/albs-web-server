import logging
import typing

import dramatiq
from sqlalchemy import update

from alws.constants import DRAMATIQ_TASK_TIMEOUT, TestTaskStatus
from alws.crud import test as t_crud
from alws.database import Session
from alws.dramatiq import event_loop
from alws.models import TestTask
from alws.schemas.test_schema import TestTaskResult


__all__ = ['complete_test_task']


async def _complete_test_task(task_id: int, task_result: TestTaskResult):
    async with Session() as db, db.begin():
        try:
            await t_crud.complete_test_task(db, task_id, task_result)
        except Exception as e:
            logging.exception(
                'Cannot set test task "%d" result, marking as failed.'
                'Error: %s', task_id, str(e))
            await db.rollback()
            await db.execute(update(TestTask).where(
                TestTask.id == task_id).values(status=TestTaskStatus.FAILED))


@dramatiq.actor(max_retries=2, priority=5, time_limit=DRAMATIQ_TASK_TIMEOUT)
def complete_test_task(task_id: int, payload: typing.Dict[str, typing.Any]):
    event_loop.run_until_complete(
        _complete_test_task(task_id, TestTaskResult(**payload)))

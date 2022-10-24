from contextlib import asynccontextmanager
import logging

import dramatiq
from sqlalchemy import update

from alws.constants import DRAMATIQ_TASK_TIMEOUT, ErrataReleaseStatus
from alws.crud.errata import release_errata_record
from alws.dramatiq import event_loop
from alws.dependencies import get_db
from alws.models import ErrataRecord

__all__ = ["release_errata"]


async def _release_errata_record(record_id: str):
    async with asynccontextmanager(get_db)() as session:
        await session.execute(
            update(ErrataRecord)
            .where(ErrataRecord.id == record_id)
            .values(
                release_status=ErrataReleaseStatus.IN_PROGRESS,
                last_release_log=None,
            )
        )
        await session.commit()
    try:
        logging.info("Record release %s has been started", record_id)
        await release_errata_record(session, record_id)
        logging.info("Record %s succesfully released", record_id)
    except Exception as exc:
        # Before saving release log and status,
        # we should rollback session changes manually
        await session.rollback()
        await session.execute(
            update(ErrataRecord)
            .where(ErrataRecord.id == record_id)
            .values(
                release_status=ErrataReleaseStatus.FAILED,
                last_release_log=str(exc),
            )
        )
        await session.commit()
        logging.exception("Cannot release %s record:", record_id)


@dramatiq.actor(
    max_retries=0,
    priority=0,
    queue_name="errata",
    time_limit=DRAMATIQ_TASK_TIMEOUT,
)
def release_errata(record_id: str):
    event_loop.run_until_complete(_release_errata_record(record_id))

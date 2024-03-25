import typing

import dramatiq

from alws.constants import DRAMATIQ_TASK_TIMEOUT
from alws.crud.errata import (
    bulk_errata_records_release,
    release_errata_record,
)
from alws.dramatiq import event_loop
from alws.utils.fastapi_sqla_setup import setup_all

__all__ = ["release_errata"]


async def _release_errata_record(record_id: str, platform_id: int, force: bool):
    await release_errata_record(
        record_id,
        platform_id,
        force,
    )


async def _bulk_errata_records_release(records_ids: typing.List[str]):
    await bulk_errata_records_release(records_ids)


@dramatiq.actor(
    max_retries=0,
    priority=0,
    queue_name="errata",
    time_limit=DRAMATIQ_TASK_TIMEOUT,
)
def release_errata(record_id: str, platform_id: int, force: bool):
    event_loop.run_until_complete(setup_all())
    event_loop.run_until_complete(
        _release_errata_record(
            record_id,
            platform_id,
            force,
        )
    )


@dramatiq.actor(
    max_retries=0,
    priority=0,
    queue_name="errata",
    time_limit=DRAMATIQ_TASK_TIMEOUT,
)
def bulk_errata_release(records_ids: typing.List[str]):
    event_loop.run_until_complete(setup_all())
    event_loop.run_until_complete(_bulk_errata_records_release(records_ids))

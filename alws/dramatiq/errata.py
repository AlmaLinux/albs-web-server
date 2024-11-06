import typing

import dramatiq

from alws.constants import DRAMATIQ_TASK_TIMEOUT
from alws.crud.errata import (
    bulk_errata_records_release,
    bulk_new_errata_records_release,
    create_new_errata_record,
    release_errata_record,
    release_new_errata_record,
    reset_matched_erratas_packages_threshold,
)
from alws.dramatiq import event_loop
from alws.utils.fastapi_sqla_setup import setup_all

__all__ = ["release_errata"]


async def _create_new_errata(errata):
     await create_new_errata_record(errata)


async def _release_new_errata_record(
    record_id: str, platform_id: int, force: bool
):
    await release_new_errata_record(
        record_id,
        platform_id,
        force,
    )


async def _release_errata_record(record_id: str, platform_id: int, force: bool):
    await release_errata_record(
        record_id,
        platform_id,
        force,
    )


async def _bulk_errata_records_release(
    records_ids: typing.List[str], force: bool = False
):
    await bulk_errata_records_release(records_ids, force)


async def _bulk_new_errata_records_release(
    records_ids: typing.List[str], force: bool = False
):
    await bulk_new_errata_records_release(records_ids, force)


async def _reset_matched_erratas_packages_threshold(issued_date: str):
    await reset_matched_erratas_packages_threshold(issued_date)


@dramatiq.actor(
    max_retries=0,
    priority=0,
    queue_name="errata",
    time_limit=DRAMATIQ_TASK_TIMEOUT,
)
def create_new_errata(errata):
    event_loop.run_until_complete(setup_all())
    event_loop.run_until_complete(
        _create_new_errata(errata)
    )


@dramatiq.actor(
    max_retries=0,
    priority=0,
    queue_name="errata",
    time_limit=DRAMATIQ_TASK_TIMEOUT,
)
def release_new_errata(record_id: str, platform_id: int, force: bool = False):
    event_loop.run_until_complete(setup_all())
    event_loop.run_until_complete(
        _release_new_errata_record(
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
def bulk_errata_release(records_ids: typing.List[str], force: bool = False):
    event_loop.run_until_complete(setup_all())
    event_loop.run_until_complete(
        _bulk_errata_records_release(records_ids, force)
    )


@dramatiq.actor(
    max_retries=0,
    priority=0,
    queue_name="errata",
    time_limit=DRAMATIQ_TASK_TIMEOUT,
)
def bulk_new_errata_release(records_ids: typing.List[str], force: bool = False):
    event_loop.run_until_complete(setup_all())
    event_loop.run_until_complete(
        _bulk_new_errata_records_release(records_ids, force)
    )


@dramatiq.actor(
    max_retries=0,
    priority=0,
    queue_name="errata",
    time_limit=DRAMATIQ_TASK_TIMEOUT,
)
def reset_records_threshold(issued_date: str):
    event_loop.run_until_complete(setup_all())
    event_loop.run_until_complete(
        _reset_matched_erratas_packages_threshold(issued_date)
    )

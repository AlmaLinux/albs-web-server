import typing

import dramatiq

from alws.constants import DRAMATIQ_TASK_TIMEOUT
from alws.crud.errata import release_errata_record, bulk_errata_records_release
from alws.dramatiq import event_loop
from alws.utils.db_utils import prepare_mappings

__all__ = ["release_errata"]


@dramatiq.actor(
    max_retries=0,
    priority=0,
    queue_name="errata",
    time_limit=DRAMATIQ_TASK_TIMEOUT,
)
def release_errata(record_id: str):
    event_loop.run_until_complete(
        prepare_mappings(release_errata_record)(record_id))


@dramatiq.actor(
    max_retries=0,
    priority=0,
    queue_name="errata",
    time_limit=DRAMATIQ_TASK_TIMEOUT,
)
def bulk_errata_release(records_ids: typing.List[str]):
    event_loop.run_until_complete(
        prepare_mappings(bulk_errata_records_release)(records_ids))

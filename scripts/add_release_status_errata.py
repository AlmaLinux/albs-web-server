import logging
import os
import sys
import typing

sys.path.append(os.path.dirname(os.path.dirname(__file__)))

from fastapi_sqla import open_session
from sqlalchemy import select

from alws.constants import ErrataReleaseStatus
from alws.models import ErrataRecord
from alws.pulp_models import UpdateRecord
from alws.utils.fastapi_sqla_setup import sync_setup

logging.basicConfig(
    level=logging.INFO,
    handlers=[
        logging.StreamHandler(),
    ],
)


def main():
    logging.info("Start checking release status for ALBS errata records")
    sync_setup()
    with open_session(key="pulp") as pulp_db, open_session() as albs_db:
        pulp_records: typing.List[UpdateRecord.id] = (
            pulp_db.execute(select(UpdateRecord.id)).scalars().all()
        )
        for albs_record in (
            albs_db.execute(select(ErrataRecord)).scalars().all()
        ):
            albs_record: ErrataRecord
            if albs_record.id not in pulp_records:
                albs_record.release_status = ErrataReleaseStatus.NOT_RELEASED
                logging.info(
                    "Record %s marked as 'not released'", albs_record.id
                )
                continue
            albs_record.release_status = ErrataReleaseStatus.RELEASED
            logging.info("Record %s marked as 'released'", albs_record.id)
    logging.info("Checking ALBS errata records is complete")


if __name__ == "__main__":
    main()

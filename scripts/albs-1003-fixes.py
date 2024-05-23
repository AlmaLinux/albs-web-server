import asyncio
import datetime
import logging
import os
import sys

from sqlalchemy import select

sys.path.append(os.path.dirname(os.path.dirname(__file__)))

from fastapi_sqla import open_async_session, open_session

from alws.dependencies import get_async_db_key
from alws.models import ErrataRecord
from alws.pulp_models import UpdateRecord
from alws.utils.errata import debrand_description_and_title
from alws.utils.fastapi_sqla_setup import setup_all

logging.basicConfig(
    format="%(asctime)s %(levelname)-8s %(message)s",
    level=logging.INFO,
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("albs-1003-fixes.log"),
    ],
)


async def main():
    affected_updateinfos = {}
    await setup_all()
    async with open_async_session(get_async_db_key()) as session:
        records = await session.execute(
            select(ErrataRecord).where(
                ErrataRecord.original_description.like("%[rhel%")
            )
        )
        for record in records.scalars().all():
            debranded_description = debrand_description_and_title(
                record.original_description,
            )
            record.original_description = debranded_description
            affected_updateinfos[record.id] = debranded_description

    with open_session(key="pulp") as pulp_session:
        records = pulp_session.execute(
            select(UpdateRecord).where(
                UpdateRecord.id.in_(list(affected_errata_ids)),
            )
        )
        for record in records:
            record.updated_date = datetime.datetime.utcnow().strftime(
                "%Y-%m-%d %H:%M:%S",
            )
            record.description = affected_updateinfos[record.id]
            session.flush()


if __name__ == "__main__":
    asyncio.run(main())

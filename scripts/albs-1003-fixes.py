import asyncio
import datetime
import logging
import os
import sys
from contextlib import asynccontextmanager

from sqlalchemy import select

sys.path.append(os.path.dirname(os.path.dirname(__file__)))

from alws.dependencies import get_db, get_pulp_db
from alws.models import ErrataRecord
from alws.pulp_models import UpdateRecord
from alws.utils.errata import debrand_description_and_title

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
    async with asynccontextmanager(get_db)() as session, session.begin():
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
        await session.commit()
    with get_pulp_db() as pulp_session:
        records = session.execute(
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
        session.commit()


if __name__ == "__main__":
    asyncio.run(main())

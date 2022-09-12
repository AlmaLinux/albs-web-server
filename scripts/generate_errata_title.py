import asyncio
import os
import re
import sys
from contextlib import asynccontextmanager

from sqlalchemy.future import select
sys.path.append(os.path.dirname(os.path.dirname(__file__)))

from alws import models
from alws.dependencies import get_db


async def main():
    severity_regex = re.compile('^(Important|Critical|Moderate|Low): ')

    updated_records = []
    async with asynccontextmanager(get_db)() as db, db.begin():
        errata_records = (await db.execute(
            select(models.ErrataRecord))).scalars().all()
        for record in errata_records:
            clean_title = severity_regex.sub('', record.original_title)
            record.title = f'{record.id}: {clean_title} ({record.severity})'
            record.oval_title = f'{record.id}: {clean_title} ({record.severity})'
            updated_records.append(record)
        db.add_all(updated_records)
        await db.commit()


if __name__ == '__main__':
    asyncio.run(main())

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
    module_regex = re.compile('Module ([\d\w\-\_]+:[\d\.\w]+) is enabled')

    updated_records = []
    async with asynccontextmanager(get_db)() as db, db.begin():
        errata_records = (await db.execute(
            select(models.ErrataRecord))).scalars().all()
        for record in errata_records:
            match = module_regex.findall(str(record.original_criteria))
            if match:
                record.module = match[0]
                updated_records.append(record)
        db.add_all(updated_records)
        await db.commit()


if __name__ == '__main__':
    asyncio.run(main())

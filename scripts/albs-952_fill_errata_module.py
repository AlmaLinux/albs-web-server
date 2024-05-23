import asyncio
import os
import re
import sys
from contextlib import asynccontextmanager

from fastapi_sqla import open_async_session
from sqlalchemy.future import select

sys.path.append(os.path.dirname(os.path.dirname(__file__)))

from alws import models
from alws.dependencies import get_async_db_key
from alws.utils.fastapi_sqla_setup import setup_all


async def main():
    module_regex = re.compile('Module ([\d\w\-\_]+:[\d\.\w]+) is enabled')

    updated_records = []
    await setup_all()
    async with open_async_session(key=get_async_db_key()) as db:
        errata_records = (
            (await db.execute(select(models.ErrataRecord))).scalars().all()
        )
        for record in errata_records:
            match = module_regex.findall(str(record.original_criteria))
            if match:
                record.module = match[0]
                updated_records.append(record)
        db.add_all(updated_records)


if __name__ == '__main__':
    asyncio.run(main())

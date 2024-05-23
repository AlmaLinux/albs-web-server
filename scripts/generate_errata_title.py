import asyncio
import os
import re
import sys

from fastapi_sqla import open_async_session
from sqlalchemy.future import select

sys.path.append(os.path.dirname(os.path.dirname(__file__)))

from alws import models
from alws.dependencies import get_async_db_key
from alws.utils.fastapi_sqla_setup import setup_all


async def main():
    severity_regex = re.compile('^(Important|Critical|Moderate|Low): ')

    updated_records = []
    await setup_all()
    async with open_async_session(key=get_async_db_key()) as db:
        errata_records = (
            (await db.execute(select(models.ErrataRecord))).scalars().all()
        )
        for record in errata_records:
            clean_title = severity_regex.sub('', record.original_title)
            record.title = f'{record.id}: {clean_title} ({record.severity})'
            record.oval_title = (
                f'{record.id}: {clean_title} ({record.severity})'
            )
            updated_records.append(record)
        db.add_all(updated_records)


if __name__ == '__main__':
    asyncio.run(main())

import asyncio
import os
import sys
from contextlib import asynccontextmanager

from sqlalchemy import update
from sqlalchemy.future import select

sys.path.append(os.path.dirname(os.path.dirname(__file__)))

from alws import models
from alws.constants import DEFAULT_PRODUCT
from alws.dependencies import get_db


async def main():
    async with asynccontextmanager(get_db)() as db, db.begin():
        product_id = (await db.execute(select(models.Product.id).where(
            models.Product.name == DEFAULT_PRODUCT))).scalar()
        # Assign all previous releases to AlmaLinux product
        await db.execute(update(models.Release).where(
            models.Release.product_id.is_(None)).values(product_id=product_id))
        # Set is_community flag for AlmaLinux product to False
        # to use usual release logic
        await db.execute(update(models.Product).where(
            models.Product.name == DEFAULT_PRODUCT).values(is_community=False))


if __name__ == '__main__':
    asyncio.run(main())

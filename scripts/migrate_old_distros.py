import logging
import os
import sys

sys.path.append(os.path.dirname(os.path.dirname(__file__)))

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from alws import models
from alws.database import SyncSession


def migrate_old_records():
    logging.basicConfig(level=logging.DEBUG)
    with SyncSession() as session:
        with session.begin():
            if not hasattr(models, 'Distribution'):
                logging.debug('Distribution model already deleted')
                return
            items_to_insert = []
            old_db_records = (
                session.execute(
                    select(models.Distribution).options(
                        selectinload(models.Distribution.builds),
                        selectinload(models.Distribution.platforms),
                        selectinload(models.Distribution.repositories),
                        selectinload(models.Distribution.owner),
                        selectinload(models.Distribution.team),
                    ),
                )
                .scalars()
                .all()
            )
            logging.debug("Total distributions: %s", len(old_db_records))
            for old_db_record in old_db_records:
                logging.debug("Proccessing distribution with id=%s",
                              old_db_record.id)
                new_db_record = models.Product(
                    name=old_db_record.name,
                    owner=old_db_record.owner,
                    team=old_db_record.team,
                    title=old_db_record.name,
                )
                for attr in ("builds", "platforms", "repositories"):
                    old_db_collection = getattr(old_db_record, attr, [])
                    new_db_collection = getattr(new_db_record, attr, [])
                    for coll_item in old_db_collection:
                        new_db_collection.append(coll_item)
                items_to_insert.append(new_db_record)
                logging.debug(
                    "Proccessing distribution with id=%s is finished",
                    old_db_record.id,
                )
            session.add_all(items_to_insert)
            session.commit()


if __name__ == '__main__':
    migrate_old_records()

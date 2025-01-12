import datetime
import os
import json
from enum import Enum
from pathlib import Path

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from sqlalchemy.inspection import inspect
from sqlalchemy.dialects.postgresql import JSONB

from alws.models import NewErrataRecord


def serialize_model(instance, seen=None):
    if seen is None:
        seen = set()

    if instance in seen:
        return {"id": getattr(instance, "id", None)}

    seen.add(instance)

    data = {}
    for column in inspect(instance).mapper.column_attrs:
        value = getattr(instance, column.key)

        if isinstance(value, Enum):
            data[column.key] = value.name
        elif isinstance(value, datetime.datetime):
            data[column.key] = value.isoformat()
        elif isinstance(column.expression.type, JSONB):
            data[column.key] = json.dumps(value)
        else:
            data[column.key] = value

    for relationship in inspect(instance).mapper.relationships:
        related_value = getattr(instance, relationship.key)
        if related_value is None:
            data[relationship.key] = None
        elif relationship.uselist:
            data[relationship.key] = [
                serialize_model(item, seen) for item in related_value
            ]
        else:
            data[relationship.key] = serialize_model(related_value, seen)
    return data


if __name__ == '__main__':
    sqlalchemy_url = os.getenv('SQLALCHEMY_URL')
    RECORDS_QTY = 20

    engine = create_engine(sqlalchemy_url, echo=False)
    session = Session(engine)
    stmt = (
        select(NewErrataRecord)
        .where(NewErrataRecord.id.like('ALSA%'))
        .where(NewErrataRecord.criteria != 'null')
    )
    errata_records = session.execute(stmt).scalars().fetchmany(RECORDS_QTY)

    serialized_records = [serialize_model(rec) for rec in errata_records]

    dst_path = Path(__file__).parent / 'samples/new_errata_records.json'
    with dst_path.open('w', encoding='utf-8') as f:
        json.dump(serialized_records, f, indent=4)

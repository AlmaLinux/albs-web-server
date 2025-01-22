import datetime
import json
import logging
import os
import sys
from enum import Enum
from pathlib import Path

import sqlalchemy
from dotenv import load_dotenv
from sqlalchemy import create_engine, select
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.inspection import inspect
from sqlalchemy.orm import Session

sys.path.append(str(Path(__file__).parents[1]))
load_dotenv('vars.env')


from alws.models import NewErrataRecord, NewErrataPackage, Platform


def serialize_model(instance, seen=None, exclude_models=None):
    seen = set() if seen is None else seen
    exclude_models = [] if exclude_models is None else exclude_models

    if type(instance) in exclude_models:
        return None

    if instance in seen:
        return {"id": getattr(instance, "id", None)}

    seen.add(instance)

    logging.info('Serializing %s', instance.__class__.__name__)

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
            if type(related_value[0]) in exclude_models:
                data[relationship.key] = []
                continue
            data[relationship.key] = [
                serialize_model(item, seen, exclude_models)
                for item in related_value
            ]
        else:
            data[relationship.key] = serialize_model(
                related_value, seen, exclude_models
            )

    return data


def deserialize_model(cls, data):
    instance = cls()

    if data is None:
        return instance

    for column in inspect(cls).columns:
        value = data.get(column.key)

        if value is None:
            continue

        if isinstance(column.type, sqlalchemy.Enum):
            enum_class = column.type.python_type
            value = enum_class[value]

        elif isinstance(column.type, sqlalchemy.DateTime):
            value = datetime.datetime.fromisoformat(value)

        elif isinstance(column.type, JSONB):
            value = json.loads(value) if isinstance(value, str) else value

        setattr(instance, column.key, value)

    for relationship in inspect(cls).relationships:
        related_data = data.get(relationship.key)
        if related_data is not None:
            if isinstance(related_data, dict):
                related_instance = deserialize_model(
                    relationship.mapper.class_, related_data
                )
                setattr(instance, relationship.key, related_instance)

            elif isinstance(related_data, list):
                related_instances = [
                    deserialize_model(relationship.mapper.class_, item)
                    for item in related_data
                ]
                setattr(instance, relationship.key, related_instances)

    return instance


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO, handlers=[logging.StreamHandler()])

    sqlalchemy_url = os.getenv('SQLALCHEMY_URL')

    engine = create_engine(sqlalchemy_url, echo=False)
    session = Session(engine)
    stmt = select(NewErrataRecord).where(
        NewErrataRecord.id.in_((
            'ALSA-2025:0281',
            'ALSA-2025:0325',
            'ALSA-2024:9644',
            'ALSA-2024:6964',
        ))
    )
    errata_records = session.execute(stmt).scalars().fetchall()

    serialized_records = [
        serialize_model(rec, exclude_models=[NewErrataPackage, Platform])
        for rec in errata_records
    ]

    dst_path = (
        Path(__file__).parents[1] / 'tests/samples/new_errata_records.json'
    )
    with dst_path.open('w', encoding='utf-8') as f:
        json.dump(serialized_records, f, indent=4)

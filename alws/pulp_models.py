import uuid
from datetime import datetime
from typing import List

import sqlalchemy
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from alws.database import PulpBase


class UpdateRecord(PulpBase):
    __tablename__ = 'rpm_updaterecord'

    content_ptr_id = sqlalchemy.Column(UUID(as_uuid=True), primary_key=True)
    id = sqlalchemy.Column(sqlalchemy.Text)
    issued_date = sqlalchemy.Column(sqlalchemy.Text)
    updated_date = sqlalchemy.Column(sqlalchemy.Text)
    description = sqlalchemy.Column(sqlalchemy.Text)
    fromstr = sqlalchemy.Column(sqlalchemy.Text)
    status = sqlalchemy.Column(sqlalchemy.Text)
    title = sqlalchemy.Column(sqlalchemy.Text)
    summary = sqlalchemy.Column(sqlalchemy.Text)
    version = sqlalchemy.Column(sqlalchemy.Text)
    type = sqlalchemy.Column(sqlalchemy.Text)
    severity = sqlalchemy.Column(sqlalchemy.Text)
    solution = sqlalchemy.Column(sqlalchemy.Text)
    release = sqlalchemy.Column(sqlalchemy.Text)
    rights = sqlalchemy.Column(sqlalchemy.Text)
    pushcount = sqlalchemy.Column(sqlalchemy.Text)
    digest = sqlalchemy.Column(sqlalchemy.Text)
    reboot_suggested = sqlalchemy.Column(sqlalchemy.Boolean)

    collections: List['UpdateCollection'] = relationship('UpdateCollection')


class UpdateCollection(PulpBase):
    __tablename__ = 'rpm_updatecollection'

    pulp_id = sqlalchemy.Column(UUID(as_uuid=True), primary_key=True)
    pulp_created = sqlalchemy.Column(sqlalchemy.DATETIME)
    pulp_last_updated = sqlalchemy.Column(sqlalchemy.DATETIME)

    name = sqlalchemy.Column(sqlalchemy.Text)
    shortname = sqlalchemy.Column(sqlalchemy.Text)
    module = sqlalchemy.Column(sqlalchemy.JSON, nullable=True)

    update_record_id = sqlalchemy.Column(
        UUID(as_uuid=True),
        sqlalchemy.ForeignKey(UpdateRecord.content_ptr_id),
        nullable=False
    )
    packages: List['UpdatePackage'] = relationship('UpdatePackage')


class UpdatePackage(PulpBase):
    __tablename__ = 'rpm_updatecollectionpackage'

    pulp_id = sqlalchemy.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    pulp_created = sqlalchemy.Column(sqlalchemy.DATETIME, default=datetime.now)
    pulp_last_updated = sqlalchemy.Column(sqlalchemy.DATETIME, default=datetime.now)
    arch = sqlalchemy.Column(sqlalchemy.Text)
    filename = sqlalchemy.Column(sqlalchemy.Text)
    name = sqlalchemy.Column(sqlalchemy.Text)
    version = sqlalchemy.Column(sqlalchemy.Text)
    release = sqlalchemy.Column(sqlalchemy.Text)
    epoch = sqlalchemy.Column(sqlalchemy.Text)
    reboot_suggested = sqlalchemy.Column(sqlalchemy.Boolean, default=False)
    relogin_suggested = sqlalchemy.Column(sqlalchemy.Boolean, default=False)
    restart_suggested = sqlalchemy.Column(sqlalchemy.Boolean, default=False)
    src = sqlalchemy.Column(sqlalchemy.Text)
    sum = sqlalchemy.Column(sqlalchemy.Text)
    update_collection_id = sqlalchemy.Column(
        UUID(as_uuid=True),
        sqlalchemy.ForeignKey(UpdateCollection.pulp_id),
        nullable=False
    )
    sum_type = sqlalchemy.Column(sqlalchemy.Integer)
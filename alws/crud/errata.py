from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import selectinload
from sqlalchemy.sql.expression import func

from alws import models
from alws.schemas.errata_schema import BaseErrataRecord


async def create_errata_record(db, errata: BaseErrataRecord):
    items_to_insert = []
    db_errata = models.ErrataRecord(
        id=errata.id,
        platform_id=1,  # TODO
        summary=None,
        solution=None,
        issued_date=errata.issued_date,
        updated_date=errata.updated_date,
        description=None,
        original_description=errata.description,
        title=None,
        original_title=errata.title,
        contact_mail="",  # TODO,
        status=errata.status,
        version=errata.version,
        severity=errata.severity,
        rights="",  # TODO
        definition_id=errata.definition_id,
        definition_version=errata.definition_version,
        definition_class=errata.definition_class,
        affected_cpe=errata.affected_cpe,
        criteria=None,
        original_criteria=errata.criteria,
        tests=None,
        original_tests=errata.tests,
        objects=None,
        original_objects=errata.objects,
        states=None,
        original_states=errata.states,
    )
    items_to_insert.append(db_errata)
    for ref in errata.references:
        db_reference = models.ErrataReference(
            href=ref.href,
            ref_id=ref.ref_id,
            title="",  # TODO
        )
        db_errata.references.append(db_reference)
        items_to_insert.append(db_reference)
        for cve in ref.cves:
            db_cve = models.ErrataCVE(
                cvss3=cve.cvss3,
                cwe=cve.cwe,
                impact=cve.impact,
                public=cve.public,
            )
            db_reference.cves.append(db_cve)
            items_to_insert.append(db_cve)
    for package in errata.packages:
        db_package = models.ErrataPackage(
            name=package.name,
            version=package.version,
            release=package.release,
            epoch=package.epoch,
            arch=package.arch,
            source_srpm=None,
            reboot_suggested=False,  # TODO
        )
        db_errata.packages.append(db_package)
        items_to_insert.append(db_package)
    db.add_all(items_to_insert)
    await db.commit()


async def list_errata_records(
    db, errata_record_id: Optional[str] = None, page: Optional[int] = None
):
    query = (
        select(models.ErrataRecord)
        .options(
            selectinload(models.ErrataRecord.packages),
            selectinload(models.ErrataRecord.references).selectinload(
                models.ErrataReference.cves
            ),
        )
        .order_by(models.ErrataRecord.id.desc())
    )
    if page:
        query = query.slice(10 * page - 10, 10 * page)
    if errata_record_id is not None:
        query = query.where(models.ErrataRecord.id == errata_record_id)
    if page:
        return {
            "total_records": (
                await db.execute(func.count(models.ErrataRecord.id))
            ).scalar(),
            "records": (await db.execute(query)).scalars().all(),
            "current_page": page,
        }
    return (await db.execute(query)).scalars().first()

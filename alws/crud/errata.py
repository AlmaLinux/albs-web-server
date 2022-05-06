from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import selectinload, load_only
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
        db_cve = None
        if ref.cve:
            db_cve = await db.execute(select(models.ErrataCVE).where(models.ErrataCVE.id == ref.cve.id))
            db_cve = db_cve.scalars().first()
            if db_cve is None:
                db_cve = models.ErrataCVE(
                    id=ref.cve.id,
                    cvss3=ref.cve.cvss3,
                    cwe=ref.cve.cwe,
                    impact=ref.cve.impact,
                    public=ref.cve.public,
                )
                items_to_insert.append(db_cve)
        db_reference = models.ErrataReference(
            href=ref.href,
            ref_id=ref.ref_id,
            title="",  # TODO
            cve=db_cve
        )
        db_errata.references.append(db_reference)
        items_to_insert.append(db_reference)
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
    await db.refresh(db_errata)
    return db_errata


async def get_errata_record(db, errata_record_id: str):
    options = [
        selectinload(models.ErrataRecord.packages),
        selectinload(models.ErrataRecord.references).selectinload(
            models.ErrataReference.cve
        ),
    ]
    query = (
        select(models.ErrataRecord)
        .options(*options)
        .order_by(models.ErrataRecord.updated_date.desc())
        .where(models.ErrataRecord.id == errata_record_id)
    )
    return (await db.execute(query)).scalars().first()


async def list_errata_records(
    db,
    page: Optional[int] = None,
    compact: Optional[bool] = False,
    errata_id: Optional[str] = None,
    title: Optional[str] = None,
    platform: Optional[str] = None,
    cve_id: Optional[str] = None,
):
    options = []
    if compact:
        options.append(
            load_only(models.ErrataRecord.id, models.ErrataRecord.updated_date)
        )
    else:
        options.extend(
            [
                selectinload(models.ErrataRecord.packages),
                selectinload(models.ErrataRecord.references).selectinload(
                    models.ErrataReference.cve
                ),
            ]
        )
    query = (
        select(models.ErrataRecord)
        .options(*options)
        .order_by(models.ErrataRecord.updated_date.desc())
    )
    if errata_id:
        query = query.filter(models.ErrataRecord.id.like(f"%{errata_id}%"))
    if title:
        query = query.filter(models.ErrataRecord.title.like(f"%{title}%"))
    if platform:
        query = query.filter(models.ErrataRecord.platform_id == platform)
    if cve_id:
        query = query.filter(models.ErrataCVE.id.like(f"%{cve_id}%"))
    if page:
        query = query.slice(10 * page - 10, 10 * page)
    return {
        "total_records": (
            await db.execute(func.count(models.ErrataRecord.id))
        ).scalar(),
        "records": (await db.execute(query)).scalars().all(),
        "current_page": page,
    }

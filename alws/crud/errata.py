import re
from typing import Optional

from sqlalchemy import select, or_, and_ 
from sqlalchemy.orm import selectinload, load_only
from sqlalchemy.sql.expression import func

from alws import models
from alws.schemas.errata_schema import BaseErrataRecord
from alws.utils.pulp_client import PulpClient
from alws.config import settings


def clean_release(release):
    release = re.sub(r"\.module.*$", "", release)
    return re.sub(r"\.el\d+.*$", "", release)


async def load_platform_packages(db, platform_id):
    platform = await db.execute(
        select(models.Platform)
        .where(models.Platform.id == platform_id)
        .options(selectinload(models.Platform.repos))
    )
    platform = platform.scalars().first()
    cache = {}
    pulp = PulpClient(settings.pulp_host, settings.pulp_user, settings.pulp_password)
    pkg_fields = ",".join(
        ["name", "version", "release", "arch", "pulp_href", "rpm_sourcerpm"]
    )
    for repo in platform.repos:
        if not repo.production:
            continue
        latest_version = await pulp.get_repo_latest_version(repo.pulp_href)
        async for pkg in pulp.iter_repo_packages(
            latest_version, limit=25000, fields=pkg_fields
        ):
            short_pkg_name = "-".join(
                [
                    pkg["name"],
                    pkg["version"],
                    clean_release(pkg["release"]),
                ]
            )
            if not cache.get(short_pkg_name):
                cache[short_pkg_name] = {}
            if not cache[short_pkg_name].get(pkg["arch"]):
                cache[short_pkg_name][pkg["arch"]] = []
            cache[short_pkg_name][pkg["arch"]].append(
                {"pulp_href": pkg["pulp_href"], "source_srpm": pkg["rpm_sourcerpm"]}
            )
    return cache


async def search_for_albs_packages(db, errata_package, prod_repos_cache):
    items_to_insert = []
    name_query = "-".join(
        [
            errata_package.name,
            errata_package.version,
            clean_release(errata_package.release),
        ]
    )
    for prod_package in prod_repos_cache.get(name_query, {}).get(
        errata_package.arch, []
    ):
        mapping = models.ErrataToALBSPackage(
            pulp_href=prod_package["pulp_href"],
            status=models.ErrataPackageStatus.released,
        )
        errata_package.source_srpm = prod_package["source_srpm"]
        items_to_insert.append(mapping)
        errata_package.albs_packages.append(mapping)
        return items_to_insert

    query = select(models.BuildTaskArtifact).where(
        and_(
            models.BuildTaskArtifact.type == "rpm",
            models.BuildTaskArtifact.name.startswith(name_query),
        )
    )
    result = await db.execute(query)
    for package in result.scalars().all():
        # TODO: check package arch also
        mapping = models.ErrataToALBSPackage(
            albs_artifact_id=package.id, status="proposal"
        )
        # TODO: add sourcerpm name to a package right here
        if errata_package.source_srpm is None:
            pass
        items_to_insert.append(mapping)
        errata_package.albs_packages.append(mapping)
    return items_to_insert


async def create_errata_record(db, errata: BaseErrataRecord):
    items_to_insert = []
    db_errata = models.ErrataRecord(
        id=errata.id,
        platform_id=errata.platform_id,
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
            db_cve = await db.execute(
                select(models.ErrataCVE).where(models.ErrataCVE.id == ref.cve.id)
            )
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
            ref_type=ref.ref_type,
            title="",  # TODO
            cve=db_cve,
        )
        db_errata.references.append(db_reference)
        items_to_insert.append(db_reference)
    prod_repos_cache = await load_platform_packages(db, errata.platform_id)
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
        items_to_insert.extend(
            await search_for_albs_packages(db, db_package, prod_repos_cache)
        )
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
        query = query.filter(
            or_(
                models.ErrataRecord.title.like(f"%{title}%"),
                models.ErrataRecord.original_title.like(f"%{title}%"),
            )
        )
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

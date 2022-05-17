import re
import pathlib
import datetime
from typing import Optional, List

import jinja2
from sqlalchemy import select, or_, and_
from sqlalchemy.orm import selectinload, load_only
from sqlalchemy.sql.expression import func

from alws import models
from alws.schemas import errata_schema
from alws.schemas.errata_schema import BaseErrataRecord
from alws.utils.parsing import parse_rpm_nevra
from alws.utils.pulp_client import PulpClient
from alws.config import settings


def clean_release(release):
    release = re.sub(r"\.module.*$", "", release)
    return re.sub(r"\.el\d+.*$", "", release)


def errata_records_to_json(db_records: List[models.ErrataRecord]) -> List[dict]:
    response = []
    for db_record in db_records:
        record = {
            "id": db_record.id,
            "issued_date": db_record.issued_date,
            "updated_date": db_record.updated_date,
            "severity": db_record.severity,
            "title": db_record.title or db_record.original_title,
            "description": db_record.description or db_record.original_description,
            # 'type': ... # TODO
            "packages": [],
            "modules": [],
            "references": [],
        }
        for db_pkg in db_record.packages:
            # TODO: also modules
            pass
        for db_ref in db_record.references:
            record["references"].append(
                {
                    "id": db_ref.ref_id,
                    "type": db_ref.ref_type,
                    "href": db_ref.href,
                }
            )
        response.append(record)
    return response


def errata_record_to_html(record):
    template_dir = pathlib.Path(__file__).absolute().parent / "templates"
    template = (template_dir / "errata_alma_page.j2").read_text()
    errata = errata_records_to_json(record)
    return jinja2.Template(template).render(errata=errata)


# TODO: add cache for this
async def load_platform_packages(platform):
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


async def update_errata_record(
    db, update_record: errata_schema.UpdateErrataRequest
) -> models.ErrataRecord:
    record = await get_errata_record(update_record.errata_record_id)
    if update_record.title is not None:
        if update_record.title == record.original_title:
            record.title = None
        else:
            record.title = update_record.title
    if update_record.description is not None:
        if update_record.description == record.original_description:
            record.description = None
        else:
            record.description = update_record.description
    await db.commit()
    await db.refresh(record)
    return record


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
    pulp = PulpClient(
        settings.pulp_host,
        settings.pulp_user,
        settings.pulp_password,
    )
    for package in result.scalars().all():
        pulp_rpm_package = await pulp.get_rpm_package(
            package.href, include_fields=["arch", "rpm_sourcerpm"]
        )
        if pulp_rpm_package["arch"] != errata_package.arch:
            continue
        mapping = models.ErrataToALBSPackage(
            albs_artifact_id=package.id, status=models.ErrataPackageStatus.proposal
        )
        if errata_package.source_srpm is None:
            nevra = parse_rpm_nevra(pulp_rpm_package["rpm_sourcerpm"])
            errata_package.source_srpm = nevra.name
        items_to_insert.append(mapping)
        errata_package.albs_packages.append(mapping)
    return items_to_insert


async def create_errata_record(db, errata: BaseErrataRecord):
    platform = await db.execute(
        select(models.Platform)
        .where(models.Platform.id == errata.platform_id)
        .options(selectinload(models.Platform.repos))
    )
    platform = platform.scalars().first()
    items_to_insert = []
    description = re.sub(
        r'(?is)Red\s?hat(\s+Enterprise(\s+Linux)(\s+\d.\d*)?)?',
        'AlmaLinux',
        errata.description
    )
    # ALSO old id from title, also RHEL from everything
    title = re.sub(
        r'(?is)Red\s?hat(\s+Enterprise(\s+Linux)(\s+\d.\d*)?)?',
        'AlmaLinux',
        errata.title
    )
    db_errata = models.ErrataRecord(
        id=re.sub(r'^RH', 'AL', errata.id),
        platform_id=errata.platform_id,
        summary=None,
        solution=None,
        issued_date=errata.issued_date,
        updated_date=errata.updated_date,
        description=None,
        original_description=description,
        title=None,
        original_title=title,
        contact_mail=platform.contact_mail,
        status=errata.status,
        version=errata.version,
        severity=errata.severity,
        rights=jinja2.Template(platform.copyright).render(
            year=datetime.datetime.now().year
        ),
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
    prod_repos_cache = await load_platform_packages(platform)
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
        "total_records": (await db.execute(func.count(models.ErrataRecord.id))).scalar(),
        "records": (await db.execute(query)).scalars().all(),
        "current_page": page,
    }


async def update_package_status(db, request):
    async with db.begin():
        errata_record = await db.execute(
            select(models.ErrataRecord)
            .where(models.ErrataRecord.id == request.errata_record_id)
            .options(
                selectinload(models.ErrataRecord.packages)
                .selectinload(models.ErrataPackage.albs_packages)
                .selectinload(models.ErrataToALBSPackage.build_artifact)
                .selectinload(models.BuildTaskArtifact.build_task)
            )
        )
        errata_record = errata_record.scalars().first()
        released_build_id = None
        released_source = None
        packages_by_source = {}
        for errata_pkg in errata_record.packages:
            if packages_by_source.get(errata_pkg.source_srpm) is None:
                packages_by_source[errata_pkg.source_srpm] = {}
            record_mapping = packages_by_source[errata_pkg.source_srpm]
            for albs_pkg in errata_pkg.albs_packages:
                if record_mapping.get(albs_pkg.build_id) is None:
                    record_mapping[albs_pkg.build_id] = []
                record_mapping[albs_pkg.build_id].append(albs_pkg)
                if all(
                    [
                        errata_pkg.id == request.errata_package_id,
                        albs_pkg.id == request.mapping_id,
                    ]
                ):
                    released_build_id = albs_pkg.build_id
                    released_source = errata_pkg.source_srpm
        for build_id, packages in packages_by_source[released_source].items():
            for pkg in packages:
                if all(
                    [
                        build_id != released_build_id,
                        request.status == models.ErrataPackageStatus.released,
                    ]
                ):
                    if pkg.status == models.ErrataPackageStatus.released:
                        raise ValueError(
                            f"There is already released package with same nevra: {pkg}"
                        )
                    pkg.status = models.ErrataPackageStatus.skipped
                if all(
                    [
                        build_id == released_build_id,
                        pkg.errata_package.source_srpm == released_source,
                    ]
                ):
                    pkg.status = request.status
    return True

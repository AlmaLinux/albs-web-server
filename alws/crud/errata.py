import re
import datetime
import collections
from typing import Optional, List

import jinja2
from sqlalchemy import select, or_, and_
from sqlalchemy.orm import selectinload, load_only
from sqlalchemy.sql.expression import func

from alws import models
from alws.schemas import errata_schema
from alws.schemas.errata_schema import BaseErrataRecord
from alws.utils.parsing import parse_rpm_nevra, clean_release
from alws.utils.pulp_client import PulpClient
from alws.config import settings
from alws.utils.errata import (
    debrand_id,
    debrand_affected_cpe_list,
    debrand_reference,
    debrand_comment,
)
from alws.utils.pulp_client import PulpClient

try:
    # FIXME: ovallib dependency should stay optional
    #        for web-server until we release it.
    from almalinux.liboval.composer import (
        Composer,
        get_test_cls_by_tag,
        get_object_cls_by_tag,
        get_state_cls_by_tag,
        get_variable_cls_by_tag,
    )
    from almalinux.liboval.rpmverifyfile_object import RpmverifyfileObject
    from almalinux.liboval.rpminfo_test import RpminfoTest
    from almalinux.liboval.rpmverifyfile_test import RpmverifyfileTest
    from almalinux.liboval.rpminfo_state import RpminfoState
    from almalinux.liboval.rpmverifyfile_state import RpmverifyfileState
    from almalinux.liboval.generator import Generator
    from almalinux.liboval.definition import Definition
    from almalinux.liboval.composer import Composer
except ImportError:
    pass


class CriteriaNode:
    def __init__(self, criteria, parent):
        self.criteria = criteria
        self.parent = parent

    def simplify(self) -> bool:
        to_remove = []
        for criteria in self.criteria["criteria"]:
            criteria_node = CriteriaNode(criteria, self)
            is_empty = criteria_node.simplify()
            if is_empty:
                to_remove.append(criteria)
        for criteria in to_remove:
            self.criteria["criteria"].remove(criteria)
        if (
            self.parent is not None
            and len(self.criteria["criterion"]) == 1
            and len(self.criteria["criteria"]) == 0
        ):
            self.parent.criteria["criterion"].append(
                self.criteria["criterion"].pop()
            )
        if (
            len(self.criteria["criteria"]) == 0
            and len(self.criteria["criterion"]) == 0
        ):
            return True
        return False


async def get_oval_xml(db, platform_name: str):
    platform = await db.execute(
        select(models.Platform).where(models.Platform.name == platform_name)
    )
    platform: models.Platform = platform.scalars().first()
    records = (
        await db.execute(
            select(models.ErrataRecord)
            .where(models.ErrataRecord.platform_id == platform.id)
            .options(
                selectinload(models.ErrataRecord.packages)
                .selectinload(models.ErrataPackage.albs_packages)
                .selectinload(models.ErrataToALBSPackage.build_artifact)
                .selectinload(models.BuildTaskArtifact.build_task),
                selectinload(models.ErrataRecord.references).selectinload(
                    models.ErrataReference.cve
                ),
            )
        )
    ).scalars().all()
    return errata_records_to_oval(records)


def errata_records_to_oval(records: List[models.ErrataRecord]):
    oval = Composer()
    generator = Generator(
        product_name="AlmaLinux OS Errata System",
        product_version="0.0.1",
        schema_version="5.10",
        timestamp=datetime.datetime.now(),
    )
    oval.generator = generator
    # TODO: add this info to platform
    gpg_keys = {
        "8": "51D6647EC21AD6EA",
        "9": "D36CB86CB86B3716",
    }
    objects = set()
    links_tracking = set()
    evra_regex = re.compile(r"(\d+):(.*)-(.*)")
    for record in records:
        rhel_evra_mapping = collections.defaultdict(dict)
        rhel_name_mapping = collections.defaultdict(set)
        for pkg in record.packages:
            albs_pkgs = [
                albs_pkg
                for albs_pkg in pkg.albs_packages
                if albs_pkg.status == models.ErrataPackageStatus.released
            ]
            for albs_pkg in albs_pkgs:
                rhel_evra = f"{pkg.epoch}:{pkg.version}-{pkg.release}"
                albs_evra = (
                    f"{albs_pkg.epoch}:{albs_pkg.version}-{albs_pkg.release}"
                )
                arch = albs_pkg.arch
                if arch == "noarch":
                    arch = pkg.arch
                rhel_evra_mapping[rhel_evra][arch] = albs_evra
                rhel_name_mapping[rhel_evra].add(albs_pkg.name)
        if not rhel_evra_mapping and not record.freezed:
            continue
        criteria_list = record.original_criteria[:]
        while criteria_list:
            new_criteria_list = []
            for criteria in criteria_list:
                new_criteria_list.extend(criteria["criteria"])
                criterion_list = []
                criterion_refs = set()
                for criterion in criteria["criterion"]:
                    criterion["ref"] = debrand_id(criterion["ref"])
                    if criterion["ref"] in criterion_refs:
                        continue
                    criterion_refs.add(criterion["ref"])
                    if criterion["comment"] == "Red Hat CoreOS 4 is installed":
                        continue
                    criterion["comment"] = debrand_comment(
                        criterion["comment"], record.platform.distr_version
                    )
                    if not record.freezed:
                        evra = evra_regex.search(criterion["comment"])
                        if evra:
                            evra = evra.group()
                            if evra not in rhel_evra_mapping.keys():
                                continue
                            package_name = criterion["comment"].split()[0]
                            if package_name not in rhel_name_mapping[rhel_evra]:
                                continue
                            # TODO: Add test mapping here
                            #       test_id: rhel_evra
                            criterion["comment"] = criterion[
                                "comment"
                            ].replace(
                                evra,
                                rhel_evra_mapping[evra][
                                    next(iter(rhel_evra_mapping[evra].keys()))
                                ],
                            )
                    criterion_list.append(criterion)
                if len(criterion_list) == 1 and re.search(
                    r"is signed with AlmaLinux OS",
                    criterion_list[0]["comment"],
                ):
                    criterion_list = []
                criteria["criterion"] = criterion_list
                links_tracking.update(
                    criterion["ref"] for criterion in criterion_list
                )
            criteria_list = new_criteria_list
        for criteria in record.original_criteria:
            criteria_node = CriteriaNode(criteria, None)
            criteria_node.simplify()
        definition = Definition.from_dict(
            {
                "id": debrand_id(record.definition_id),
                "version": record.definition_version,
                "class": record.definition_class,
                "metadata": {
                    "title": record.title
                    if record.title
                    else record.original_title,
                    "description": record.description
                    if record.description
                    else record.original_description,
                    "advisory": {
                        "from": record.contact_mail,
                        "severity": record.severity,
                        "rights": record.rights,
                        "issued_date": record.issued_date,
                        "updated_date": record.updated_date,
                        "affected_cpe_list": debrand_affected_cpe_list(
                            record.affected_cpe, record.platform.distr_version
                        ),
                        "bugzilla": [
                            {
                                "id": ref.ref_id,
                                "href": ref.href,
                                "title": ref.title,
                            }
                            for ref in record.references
                            if ref.ref_type
                            == models.ErrataReferenceType.bugzilla
                        ],
                        "cves": [
                            {
                                "name": ref.ref_id,
                                "public": datetime.datetime.strptime(
                                    # year-month-day
                                    ref.cve.public[:10], "%Y-%m-%d"
                                ).date(),
                                "href": ref.href,
                                "impact": ref.cve.impact,
                                "cwe": ref.cve.cwe,
                                "cvss3": ref.cve.cvss3,
                            }
                            for ref in record.references
                            if ref.ref_type == models.ErrataReferenceType.cve
                            and ref.cve
                        ],
                    },
                    "references": [
                        debrand_reference(
                            {
                                "id": ref.ref_id,
                                "source": ref.ref_type.value,
                                "url": ref.href,
                            },
                            record.platform.distr_version,
                        )
                        for ref in record.references
                        if ref.ref_type
                        not in [
                            models.ErrataReferenceType.cve,
                            models.ErrataReferenceType.bugzilla,
                        ]
                    ],
                },
                "criteria": record.original_criteria,
            }
        )
        oval.append_object(definition)
        for test in record.original_tests:
            test["id"] = debrand_id(test["id"])
            if test["id"] in objects:
                continue
            if test["id"] not in links_tracking:
                continue
            objects.add(test["id"])
            if get_test_cls_by_tag(test["type"]) in (
                RpminfoTest,
                RpmverifyfileTest,
            ):
                test["comment"] = debrand_comment(
                    test["comment"], record.platform.distr_version
                )
            test["object_ref"] = debrand_id(test["object_ref"])
            if test.get("state_ref"):
                test["state_ref"] = debrand_id(test["state_ref"])
            links_tracking.update([test["object_ref"], test["state_ref"]])
            oval.append_object(
                get_test_cls_by_tag(test["type"]).from_dict(test)
            )
        for obj in record.original_objects:
            obj["id"] = debrand_id(obj["id"])
            if obj["id"] in objects:
                continue
            if obj["id"] not in links_tracking:
                continue
            objects.add(obj["id"])
            if obj.get("instance_var_ref"):
                obj["instance_var_ref"] = debrand_id(obj["instance_var_ref"])
                links_tracking.add(obj["instance_var_ref"])
            if get_object_cls_by_tag(obj["type"]) == RpmverifyfileObject:
                if obj["filepath"] == "/etc/redhat-release":
                    obj["filepath"] = "/etc/almalinux-release"
            oval.append_object(
                get_object_cls_by_tag(obj["type"]).from_dict(obj)
            )
        for state in record.original_states:
            state["id"] = debrand_id(state["id"])
            if state["id"] in objects:
                continue
            if state["id"] not in links_tracking:
                continue
            if state.get("evr"):
                if state["evr"] in rhel_evra_mapping:
                    if state["arch"]:
                        state["arch"] = "|".join(
                            rhel_evra_mapping[state["evr"]].keys()
                        )
                    state["evr"] = rhel_evra_mapping[state["evr"]][
                        next(iter(rhel_evra_mapping[state["evr"]].keys()))
                    ]
            objects.add(state["id"])
            state_cls = get_state_cls_by_tag(state["type"])
            if state_cls == RpminfoState:
                if not record.freezed:
                    if state["signature_keyid"]:
                        state["signature_keyid"] = gpg_keys[
                            record.platform.distr_version
                        ].lower()
            elif state_cls == RpmverifyfileState:
                if state["name"] == "^redhat-release":
                    state["name"] = "^almalinux-release"
            oval.append_object(state_cls.from_dict(state))
        for var in record.original_variables:
            var["id"] = debrand_id(var["id"])
            if var["id"] in objects:
                continue
            if var["id"] not in links_tracking:
                continue
            objects.add(var["id"])
            oval.append_object(
                get_variable_cls_by_tag(var["type"]).from_dict(var)
            )
            for obj in record.original_objects:
                if (
                    obj["id"]
                    != var["arithmetic"]["object_component"]["object_ref"]
                ):
                    continue
                objects.add(obj["id"])
                oval.append_object(
                    get_object_cls_by_tag(obj["type"]).from_dict(obj)
                )
    return oval.dump_to_string()


async def load_platform_packages(platform: models.Platform):
    cache = {}
    pulp = PulpClient(
        settings.pulp_host, settings.pulp_user, settings.pulp_password
    )
    pkg_fields = ",".join((
        "name",
        "version",
        "release",
        "epoch",
        "arch",
        "pulp_href",
        "rpm_sourcerpm",
    ))
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
            arch_list = [pkg["arch"]]
            if pkg["arch"] == "noarch":
                arch_list = platform.arch_list
            for arch in arch_list:
                if not cache[short_pkg_name].get(arch):
                    cache[short_pkg_name][arch] = []
                cache[short_pkg_name][arch].append(pkg)
    return cache


async def update_errata_record(
    db, update_record: errata_schema.UpdateErrataRequest
) -> models.ErrataRecord:
    record = await get_errata_record(db, update_record.errata_record_id)
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
            name=prod_package["name"],
            version=prod_package["version"],
            release=prod_package["release"],
            epoch=int(prod_package["epoch"]),
            arch=prod_package["arch"],
        )
        src_nevra = parse_rpm_nevra(prod_package["rpm_sourcerpm"])
        errata_package.source_srpm = src_nevra.name
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
            package.href,
            include_fields=[
                "name",
                "version",
                "release",
                "epoch",
                "arch",
                "rpm_sourcerpm",
            ],
        )
        if pulp_rpm_package["arch"] != errata_package.arch:
            continue
        mapping = models.ErrataToALBSPackage(
            albs_artifact_id=package.id,
            status=models.ErrataPackageStatus.proposal,
            name=pulp_rpm_package["name"],
            version=pulp_rpm_package["version"],
            release=pulp_rpm_package["release"],
            epoch=int(pulp_rpm_package["epoch"]),
            arch=pulp_rpm_package["arch"],
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
    for key in ("description", "title"):
        value = getattr(errata, key)
        value = re.sub(
            r"(?is)Red\s?hat(\s+Enterprise(\s+Linux)(\s+\d.\d*)?)?",
            "AlmaLinux",
            value,
        )
        value = re.sub(r"^RH", "AL", value)
        value = re.sub(r"RHEL", "AlmaLinux", value)
        setattr(errata, key, value)
    db_errata = models.ErrataRecord(
        id=re.sub(r"^RH", "AL", errata.id),
        freezed=errata.freezed,
        platform_id=errata.platform_id,
        summary=None,
        solution=None,
        issued_date=errata.issued_date,
        updated_date=errata.updated_date,
        description=None,
        original_description=errata.description,
        title=None,
        original_title=errata.title,
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
        variables=None,
        original_variables=errata.variables,
    )
    items_to_insert.append(db_errata)
    for ref in errata.references:
        db_cve = None
        if ref.cve:
            db_cve = await db.execute(
                select(models.ErrataCVE).where(
                    models.ErrataCVE.id == ref.cve.id
                )
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
            title="",
            cve=db_cve,
        )
        db_errata.references.append(db_reference)
        items_to_insert.append(db_reference)
    html_id = db_errata.id.replace(":", "-")
    self_ref = models.ErrataReference(
        href=f"https://errata.almalinux.org/{platform.distr_version}/{html_id}.html",
        ref_id=db_errata.id,
        ref_type=models.ErrataReferenceType.self_ref,
        title=db_errata.id,
    )
    db_errata.references.append(self_ref)
    items_to_insert.append(self_ref)
    prod_repos_cache = await load_platform_packages(platform)
    for package in errata.packages:
        db_package = models.ErrataPackage(
            name=package.name,
            version=package.version,
            release=package.release,
            epoch=package.epoch,
            arch=package.arch,
            source_srpm=None,
            reboot_suggested=False,
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
        selectinload(models.ErrataRecord.packages)
        .selectinload(models.ErrataPackage.albs_packages)
        .selectinload(models.ErrataToALBSPackage.build_artifact)
        .selectinload(models.BuildTaskArtifact.build_task),
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
                selectinload(models.ErrataRecord.packages)
                .selectinload(models.ErrataPackage.albs_packages)
                .selectinload(models.ErrataToALBSPackage.build_artifact)
                .selectinload(models.BuildTaskArtifact.build_task),
                selectinload(models.ErrataRecord.references).selectinload(
                    models.ErrataReference.cve
                ),
            ]
        )

    def generate_query(count=False):
        query = select(func.count(models.ErrataRecord.id))
        if not count:
            query = select(models.ErrataRecord).options(*options)
            query = query.order_by(models.ErrataRecord.updated_date.desc())
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
            query = query.filter(models.ErrataRecord.cves.like(f"%{cve_id}%"))
        if page and not count:
            query = query.slice(10 * page - 10, 10 * page)
        return query

    return {
        "total_records": (
            await db.execute(generate_query(count=True))
        ).scalar(),
        "records": (await db.execute(generate_query())).scalars().all(),
        "current_page": page,
    }


async def update_package_status(
    db, request: List[errata_schema.ChangeErrataPackageStatusRequest]
):
    async with db.begin():
        for record in request:
            errata_record = await db.execute(
                select(models.ErrataRecord)
                .where(models.ErrataRecord.id == record.errata_record_id)
                .options(
                    selectinload(models.ErrataRecord.packages)
                    .selectinload(models.ErrataPackage.albs_packages)
                    .selectinload(models.ErrataToALBSPackage.build_artifact)
                    .selectinload(models.BuildTaskArtifact.build_task)
                )
            )
            errata_record = errata_record.scalars().first()
            record_approved = (
                record.status == models.ErrataPackageStatus.approved
            )
            for errata_pkg in errata_record.packages:
                if errata_pkg.source_srpm != record.source:
                    continue
                for albs_pkg in errata_pkg.albs_packages:
                    if albs_pkg.status == models.ErrataPackageStatus.released:
                        raise ValueError(
                            f"There is already released package with same source: {albs_pkg}"
                        )
                    if (
                        albs_pkg.build_id != record.build_id
                        and record_approved
                    ):
                        albs_pkg.status = models.ErrataPackageStatus.skipped
                    if albs_pkg.build_id == record.build_id:
                        albs_pkg.status = record.status
    return True

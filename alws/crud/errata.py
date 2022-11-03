import asyncio
import collections
import datetime
import re
from typing import (
    Any,
    DefaultDict,
    Dict,
    List,
    Optional,
    Tuple,
)
import uuid

import createrepo_c as cr
import jinja2
from sqlalchemy import select, or_, and_
from sqlalchemy.orm import selectinload, load_only, Session
from sqlalchemy.sql.expression import func
from sqlalchemy.ext.asyncio import AsyncSession

from alws import models
from alws.constants import ErrataReleaseStatus
from alws.dependencies import get_pulp_db
from alws.schemas import errata_schema
from alws.schemas.errata_schema import BaseErrataRecord
from alws.utils.errata import (
    clean_errata_title,
    get_nevra,
    get_oval_title,
    get_verbose_errata_title,
)
from alws.utils.parsing import (
    clean_release,
    parse_rpm_nevra,
    slice_list,
)
from alws.utils.pulp_client import PulpClient
from alws.config import settings
from alws.constants import (
    ErrataReferenceType,
    ErrataPackageStatus,
    ErrataReleaseStatus,
)
from alws.pulp_models import UpdateRecord, UpdatePackage, UpdateCollection
from alws.utils.errata import (
    debrand_id,
    debrand_affected_cpe_list,
    debrand_reference,
    debrand_comment,
)

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
except ImportError:
    pass


ERRATA_SOLUTION = """For details on how to apply this update, \
which includes the changes described in this advisory, refer to:

https://access.redhat.com/articles/11258"""


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
            self.parent.criteria["criterion"].append(self.criteria["criterion"].pop())
        if len(self.criteria["criteria"]) == 0 and len(self.criteria["criterion"]) == 0:
            return True
        return False


async def get_oval_xml(db: AsyncSession, platform_name: str):
    platform = await db.execute(
        select(models.Platform).where(models.Platform.name == platform_name)
    )
    platform: models.Platform = platform.scalars().first()
    records = (
        (
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
        )
        .scalars()
        .all()
    )
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
        is_freezed = record.freezed
        rhel_evra_mapping = collections.defaultdict(dict)
        rhel_name_mapping = collections.defaultdict(set)
        for pkg in record.packages:
            albs_pkgs = [
                albs_pkg
                for albs_pkg in pkg.albs_packages
                if albs_pkg.status == ErrataPackageStatus.released
            ]
            for albs_pkg in albs_pkgs:
                rhel_evra = f"{pkg.epoch}:{pkg.version}-{pkg.release}"
                albs_evra = f"{albs_pkg.epoch}:{albs_pkg.version}-{albs_pkg.release}"
                arch = albs_pkg.arch
                if arch == "noarch":
                    arch = pkg.arch
                rhel_evra_mapping[rhel_evra][arch] = albs_evra
                rhel_name_mapping[rhel_evra].add(albs_pkg.name)
        if not rhel_evra_mapping and not is_freezed:
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
                    if not is_freezed:
                        evra = evra_regex.search(criterion["comment"])
                        if evra:
                            evra = evra.group()
                            if evra not in rhel_evra_mapping.keys():
                                continue
                            package_name = criterion["comment"].split()[0]
                            if package_name not in rhel_name_mapping[evra]:
                                continue
                            # TODO: Add test mapping here
                            #       test_id: rhel_evra
                            criterion["comment"] = criterion["comment"].replace(
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
                links_tracking.update(criterion["ref"] for criterion in criterion_list)
            criteria_list = new_criteria_list
        for criteria in record.original_criteria:
            criteria_node = CriteriaNode(criteria, None)
            criteria_node.simplify()
        if record.oval_title:
            title = record.oval_title
        elif not record.oval_title and record.title:
            title = record.title
        else:
            title = record.original_title
        definition = Definition.from_dict(
            {
                "id": debrand_id(record.definition_id),
                "version": record.definition_version,
                "class": record.definition_class,
                "metadata": {
                    "title": title,
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
                            if ref.ref_type == ErrataReferenceType.bugzilla
                        ],
                        "cves": [
                            {
                                "name": ref.ref_id,
                                "public": datetime.datetime.strptime(
                                    # year-month-day
                                    ref.cve.public[:10],
                                    "%Y-%m-%d",
                                ).date(),
                                "href": ref.href,
                                "impact": ref.cve.impact,
                                "cwe": ref.cve.cwe,
                                "cvss3": ref.cve.cvss3,
                            }
                            for ref in record.references
                            if ref.ref_type == ErrataReferenceType.cve and ref.cve
                        ],
                    },
                    "references": [
                        debrand_reference(
                            {
                                "id": ref.ref_id,
                                "source": ref.ref_type.value.upper(),
                                "url": ref.href,
                            },
                            record.platform.distr_version,
                        )
                        for ref in record.references
                        if ref.ref_type
                        not in [
                            ErrataReferenceType.bugzilla,
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
            oval.append_object(get_test_cls_by_tag(test["type"]).from_dict(test))
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
            oval.append_object(get_object_cls_by_tag(obj["type"]).from_dict(obj))
        for state in record.original_states:
            state["id"] = debrand_id(state["id"])
            if state["id"] in objects:
                continue
            if state["id"] not in links_tracking:
                continue
            if state.get("evr"):
                if state["evr"] in rhel_evra_mapping:
                    if state["arch"]:
                        state["arch"] = "|".join(rhel_evra_mapping[state["evr"]].keys())
                    state["evr"] = rhel_evra_mapping[state["evr"]][
                        next(iter(rhel_evra_mapping[state["evr"]].keys()))
                    ]
            objects.add(state["id"])
            state_cls = get_state_cls_by_tag(state["type"])
            if state_cls == RpminfoState:
                if not is_freezed:
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
            oval.append_object(get_variable_cls_by_tag(var["type"]).from_dict(var))
            for obj in record.original_objects:
                if obj["id"] != var["arithmetic"]["object_component"]["object_ref"]:
                    continue
                if obj["id"] in objects:
                    continue
                objects.add(obj["id"])
                oval.append_object(get_object_cls_by_tag(obj["type"]).from_dict(obj))
    return oval.dump_to_string()


def prepare_search_params(errata_record: models.ErrataRecord) -> Dict[str, List[str]]:
    search_params = collections.defaultdict(set)
    for package in errata_record.packages:
        for attr in ("name", "version", "epoch"):
            value = str(getattr(package, attr))
            search_params[attr].add(value)
    for key, values in search_params.items():
        search_params[key] = list(values)
    return search_params


async def load_platform_packages(
    platform: models.Platform,
    search_params: DefaultDict[str, set],
    pulp: PulpClient,
    for_release: bool = False,
):
    cache = {}
    # With this minimal length for lists, we will evade
    # errors with large query path in requests
    max_list_len = 10
    pkg_fields = ",".join(
        (
            "name",
            "version",
            "release",
            "epoch",
            "arch",
            "pulp_href",
            "rpm_sourcerpm",
        )
    )
    if for_release:
        pkg_fields = ",".join(("pulp_href",))

    async def _callback(pulp_href: str):
        latest_version = await pulp.get_repo_latest_version(pulp_href)
        request_params = {"epoch__in": ",".join(search_params["epoch"])}
        for pkg_names in slice_list(list(search_params["name"]), max_list_len):
            request_params["name__in"] = ",".join(pkg_names)
            for pkg_versions in slice_list(search_params["version"], max_list_len):
                request_params["version__in"] = ",".join(pkg_versions)
                async for pkg in pulp.iter_repo_packages(
                    latest_version,
                    limit=25000,
                    fields=pkg_fields,
                    search_params=request_params,
                ):
                    if for_release:
                        key = pkg["pulp_href"]
                        if not cache.get(key):
                            cache[key] = []
                        cache[key].append(pulp_href)
                        continue
                    short_pkg_name = "-".join(
                        (
                            pkg["name"],
                            pkg["version"],
                            clean_release(pkg["release"]),
                        )
                    )
                    if not cache.get(short_pkg_name):
                        cache[short_pkg_name] = {}
                    arch_list = [pkg["arch"]]
                    if pkg["arch"] == "noarch":
                        arch_list = platform.arch_list
                    for arch in arch_list:
                        if not cache[short_pkg_name].get(arch):
                            cache[short_pkg_name][arch] = []
                        if pkg in cache[short_pkg_name][arch]:
                            continue
                        cache[short_pkg_name][arch].append(pkg)

    tasks = []
    for repo in platform.repos:
        if not repo.production:
            continue
        tasks.append(_callback(repo.pulp_href))
    await asyncio.gather(*tasks)
    return cache


async def update_errata_record(
    db: AsyncSession, update_record: errata_schema.UpdateErrataRequest
) -> models.ErrataRecord:
    record = await get_errata_record(db, update_record.errata_record_id)
    if update_record.title is not None:
        if update_record.title == record.original_title:
            record.title = None
        else:
            record.title = update_record.title
        if record.title:
            record.oval_title = get_oval_title(record.title, record.id, record.severity)
    if update_record.description is not None:
        if update_record.description == record.original_description:
            record.description = None
        else:
            record.description = update_record.description
    await db.commit()
    await db.refresh(record)
    return record


async def search_for_albs_packages(
    db: AsyncSession,
    errata_package: models.ErrataPackage,
    prod_repos_cache,
) -> List[models.ErrataToALBSPackage]:
    items_to_insert = []
    clean_package_name = "-".join(
        (
            errata_package.name,
            errata_package.version,
            clean_release(errata_package.release),
        )
    )
    for prod_package in prod_repos_cache.get(clean_package_name, {}).get(
        errata_package.arch, []
    ):
        mapping = models.ErrataToALBSPackage(
            pulp_href=prod_package["pulp_href"],
            status=ErrataPackageStatus.released,
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

    name_query = f"{errata_package.name}-{errata_package.version}"
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
        try:
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
        except Exception:
            continue
        clean_pulp_package_name = "-".join(
            (
                pulp_rpm_package["name"],
                pulp_rpm_package["version"],
                clean_release(pulp_rpm_package["release"]),
            )
        )
        if (
            pulp_rpm_package["arch"] != errata_package.arch
            and pulp_rpm_package["arch"] != "noarch"
            or clean_pulp_package_name != clean_package_name
        ):
            continue
        mapping = models.ErrataToALBSPackage(
            albs_artifact_id=package.id,
            status=ErrataPackageStatus.proposal,
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


async def create_errata_record(db: AsyncSession, errata: BaseErrataRecord):
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
    alma_errata_id = re.sub(r"^RH", "AL", errata.id)
    db_errata = models.ErrataRecord(
        id=alma_errata_id,
        freezed=errata.freezed,
        platform_id=errata.platform_id,
        release_status=ErrataReleaseStatus.NOT_RELEASED,
        summary=None,
        solution=None,
        issued_date=errata.issued_date,
        updated_date=errata.updated_date,
        description=None,
        original_description=errata.description,
        title=None,
        oval_title=get_oval_title(errata.title, alma_errata_id, errata.severity),
        original_title=get_verbose_errata_title(errata.title, errata.severity),
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
    self_ref_exists = False
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
        ref_title = ""
        if ref.ref_type in (
            ErrataReferenceType.cve.value,
            ErrataReferenceType.rhsa.value,
        ):
            ref_title = ref.ref_id
        db_reference = models.ErrataReference(
            href=ref.href,
            ref_id=ref.ref_id,
            ref_type=ref.ref_type,
            title=ref_title,
            cve=db_cve,
        )
        if ref.ref_type == ErrataReferenceType.self_ref.value:
            self_ref_exists = True
        db_errata.references.append(db_reference)
        items_to_insert.append(db_reference)
    html_id = db_errata.id.replace(":", "-")
    if not self_ref_exists:
        self_ref = models.ErrataReference(
            href=(
                f"https://errata.almalinux.org/"
                f"{platform.distr_version}/{html_id}.html"
            ),
            ref_id=db_errata.id,
            ref_type=ErrataReferenceType.self_ref,
            title=db_errata.id,
        )
        db_errata.references.append(self_ref)
        items_to_insert.append(self_ref)
    pulp = PulpClient(settings.pulp_host, settings.pulp_user, settings.pulp_password)
    search_params = prepare_search_params(errata)
    prod_repos_cache = await load_platform_packages(platform, search_params, pulp)
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


async def get_errata_record(db: AsyncSession, errata_record_id: str):
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
    db: AsyncSession,
    page: Optional[int] = None,
    compact: Optional[bool] = False,
    errata_id: Optional[str] = None,
    title: Optional[str] = None,
    platform: Optional[str] = None,
    cve_id: Optional[str] = None,
    status: Optional[ErrataReleaseStatus] = None,
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
            query = query.order_by(models.ErrataRecord.id.desc())
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
        if status:
            query = query.filter(models.ErrataRecord.release_status == status)
        if page and not count:
            query = query.slice(10 * page - 10, 10 * page)
        return query

    return {
        "total_records": (await db.execute(generate_query(count=True))).scalar(),
        "records": (await db.execute(generate_query())).scalars().all(),
        "current_page": page,
    }


async def update_package_status(
    db: AsyncSession,
    request: List[errata_schema.ChangeErrataPackageStatusRequest],
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
            record_approved = record.status == ErrataPackageStatus.approved
            for errata_pkg in errata_record.packages:
                if errata_pkg.source_srpm != record.source:
                    continue
                for albs_pkg in errata_pkg.albs_packages:
                    if albs_pkg.status == ErrataPackageStatus.released:
                        raise ValueError(
                            f"There is already released package "
                            f"with same source: {albs_pkg}"
                        )
                    if albs_pkg.build_id != record.build_id and record_approved:
                        albs_pkg.status = ErrataPackageStatus.skipped
                    if albs_pkg.build_id == record.build_id:
                        albs_pkg.status = record.status
    return True


async def release_errata_packages(
    db: AsyncSession,
    pulp_client: PulpClient,
    record: models.ErrataRecord,
    packages: List[models.ErrataToALBSPackage],
    platform: models.Platform,
    repo_href: str,
):
    repo = await pulp_client.get_by_href(repo_href)
    released_record = await pulp_client.list_updateinfo_records(
        id__in=[record.id],
        repository_version=repo["latest_version_href"],
    )
    if released_record:
        # Errata record was already released to corresponding repo
        return
    repo_stage = repo["name"].split("-")[-2]
    arch = repo["name"].split("-")[-1]
    platform_version = platform.modularity["versions"][-1]
    platform_version = platform_version["name"].replace(".", "_")
    rpm_module = None
    reboot_suggested = False
    dict_packages = []
    released_names = set()
    for errata_pkg in packages:
        pulp_pkg = await pulp_client.get_by_href(errata_pkg.get_pulp_href())
        if errata_pkg.errata_package.reboot_suggested:
            reboot_suggested = True
        if pulp_pkg["name"] in released_names:
            continue
        released_names.add(pulp_pkg["name"])
        dict_packages.append(
            {
                "name": pulp_pkg["name"],
                "release": pulp_pkg["release"],
                "version": pulp_pkg["version"],
                "epoch": pulp_pkg["epoch"],
                "arch": pulp_pkg["arch"],
                "filename": pulp_pkg["location_href"],
                "reboot_suggested": errata_pkg.errata_package.reboot_suggested,
                "src": pulp_pkg["rpm_sourcerpm"],
                "sum": pulp_pkg["sha256"],
                "sum_type": "sha256",
            }
        )
        if rpm_module:
            continue
        query = models.BuildTaskArtifact.href == errata_pkg.pulp_href
        if errata_pkg.albs_artifact_id is not None:
            query = models.BuildTaskArtifact.id == errata_pkg.albs_artifact_id
        db_pkg = await db.execute(
            select(models.BuildTaskArtifact)
            .where(query)
            .options(
                selectinload(models.BuildTaskArtifact.build_task).selectinload(
                    models.BuildTask.rpm_module
                )
            )
        )
        db_pkg = db_pkg.scalars().first()
        if not db_pkg:
            continue
        db_module = db_pkg.build_task.rpm_module
        if db_module is not None:
            rpm_module = {
                "name": db_module.name,
                "stream": db_module.stream,
                "version": int(db_module.version),
                "context": db_module.context,
                "arch": db_module.arch,
            }
    collection_name = (
        f"{platform.name.lower()}-for-{arch}-{repo_stage}-"
        f"rpms__{platform_version}_default"
    )
    default_summary = clean_errata_title(record.get_title(), severity=record.severity)
    pulp_record = {
        "id": record.id,
        "updated_date": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "issued_date": record.issued_date.strftime("%Y-%m-%d %H:%M:%S"),
        "description": record.get_description(),
        "fromstr": record.contact_mail,
        "status": record.status,
        "title": record.get_title(),
        "summary": record.summary or default_summary,
        "version": record.version,
        "type": record.get_type(),
        "severity": record.severity,
        "solution": record.solution or ERRATA_SOLUTION,
        "release": "0",
        "rights": record.rights,
        "pushcount": "1",
        "pkglist": [
            {
                "name": collection_name,
                "short": collection_name,
                "module": rpm_module,
                "packages": dict_packages,
            }
        ],
        "references": [
            {
                "href": ref.href,
                "id": ref.ref_id,
                "title": ref.title,
                "type": ref.ref_type.value,
            }
            for ref in record.references
        ],
        "reboot_suggested": reboot_suggested,
    }
    await pulp_client.add_errata_record(pulp_record, repo_href)
    await pulp_client.create_rpm_publication(repo_href)


async def prepare_updateinfo_mapping(
    db: AsyncSession,
    pulp: PulpClient,
    package_hrefs: List[str],
    blacklist_updateinfo: List[str],
) -> DefaultDict[
    str,
    List[Tuple[models.BuildTaskArtifact, dict, models.ErrataToALBSPackage]],
]:
    updateinfo_mapping = collections.defaultdict(list)
    for pkg_href in set(package_hrefs):
        db_pkg_list = (
            (
                await db.execute(
                    select(models.BuildTaskArtifact)
                    .where(
                        models.BuildTaskArtifact.href == pkg_href,
                    )
                    .options(
                        selectinload(models.BuildTaskArtifact.build_task).selectinload(
                            models.BuildTask.rpm_module
                        )
                    )
                )
            )
            .scalars()
            .all()
        )
        for db_pkg in db_pkg_list:
            errata_pkgs = await db.execute(
                select(models.ErrataToALBSPackage)
                .where(
                    or_(
                        models.ErrataToALBSPackage.albs_artifact_id == db_pkg.id,
                        models.ErrataToALBSPackage.pulp_href == pkg_href,
                    )
                )
                .options(
                    selectinload(models.ErrataToALBSPackage.errata_package),
                    selectinload(models.ErrataToALBSPackage.build_artifact),
                )
            )
            for errata_pkg in errata_pkgs.scalars().all():
                errata_id = errata_pkg.errata_package.errata_record_id
                if errata_id in blacklist_updateinfo:
                    continue
                pulp_pkg = await pulp.get_rpm_package(
                    db_pkg.href,
                    include_fields=[
                        "name",
                        "version",
                        "release",
                        "epoch",
                        "arch",
                        "location_href",
                        "sha256",
                        "rpm_sourcerpm",
                    ],
                )
                updateinfo_mapping[errata_id].append(
                    (db_pkg, pulp_pkg, errata_pkg),
                )
    return updateinfo_mapping


def append_update_packages_in_update_records(
    pulp_db: Session,
    errata_records: List[Dict[str, Any]],
    updateinfo_mapping: DefaultDict[
        str, List[Tuple[models.BuildTaskArtifact, dict, models.ErrataToALBSPackage]]
    ],
):
    with pulp_db.begin():
        for record in errata_records:
            record_uuid = uuid.UUID(record["pulp_href"].split("/")[-2])
            packages = updateinfo_mapping.get(record["id"])
            if not packages:
                continue
            pulp_record = pulp_db.execute(
                select(UpdateRecord)
                .where(UpdateRecord.content_ptr_id == record_uuid)
                .options(
                    selectinload(UpdateRecord.collections).selectinload(
                        UpdateCollection.packages
                    ),
                )
            )
            pulp_record: UpdateRecord = pulp_record.scalars().first()
            for _, pulp_pkg, pkg in packages:
                already_released = False
                collection = pulp_record.collections[0]
                collection_arch = re.search(
                    r"i686|x86_64|aarch64|ppc64le|s390x",
                    collection.name,
                ).group()
                if pulp_pkg["arch"] not in (collection_arch, "noarch"):
                    continue
                already_released = next(
                    (
                        package
                        for package in collection.packages
                        if package.filename == pulp_pkg["location_href"]
                    ),
                    None,
                )
                if already_released:
                    continue
                collection.packages.append(
                    UpdatePackage(
                        name=pulp_pkg["name"],
                        filename=pulp_pkg["location_href"],
                        arch=pulp_pkg["arch"],
                        version=pulp_pkg["version"],
                        release=pulp_pkg["release"],
                        epoch=str(pulp_pkg["epoch"]),
                        reboot_suggested=pkg.errata_package.reboot_suggested,
                        src=pulp_pkg["rpm_sourcerpm"],
                        sum=pulp_pkg["sha256"],
                        sum_type=cr.checksum_type("sha256"),
                    )
                )
                pulp_record.updated_date = datetime.datetime.now().strftime(
                    "%Y-%m-%d %H:%M:%S"
                )


async def release_errata_record(db: AsyncSession, record_id: str):
    pulp = PulpClient(
        settings.pulp_host,
        settings.pulp_user,
        settings.pulp_password,
    )
    db_record = await db.execute(
        select(models.ErrataRecord)
        .where(models.ErrataRecord.id == record_id)
        .options(
            selectinload(models.ErrataRecord.references),
            selectinload(models.ErrataRecord.packages)
            .selectinload(models.ErrataPackage.albs_packages)
            .selectinload(models.ErrataToALBSPackage.build_artifact),
            selectinload(models.ErrataRecord.platform).selectinload(
                models.Platform.repos
            ),
        )
    )
    db_record: models.ErrataRecord = db_record.scalars().first()
    search_params = prepare_search_params(db_record)
    pulp_packages = await load_platform_packages(
        db_record.platform,
        search_params,
        pulp,
        for_release=True,
    )
    repo_mapping = collections.defaultdict(list)

    errata_packages = set()
    albs_records_to_add = set()
    errata_package_names_mapping = {
        "raw": {},
        "albs": {},
    }
    for package in db_record.packages:
        for albs_package in package.albs_packages:
            if albs_package.status not in (
                ErrataPackageStatus.released,
                ErrataPackageStatus.approved,
            ):
                continue
            albs_package_pulp_href = albs_package.get_pulp_href()
            if pulp_packages.get(albs_package_pulp_href):
                for repo in pulp_packages[albs_package_pulp_href]:
                    repo_mapping[repo].append(albs_package)
                albs_package.status = ErrataPackageStatus.released
                clean_albs_pkg_nevra = get_nevra(
                    albs_package,
                    arch=albs_package.errata_package.arch,
                )
                raw_albs_pkg_nevra = get_nevra(albs_package, clean=False)
                albs_records_to_add.add(clean_albs_pkg_nevra)
                errata_package_names_mapping["albs"][
                    clean_albs_pkg_nevra
                ] = raw_albs_pkg_nevra

        clean_errata_pkg_nevra = get_nevra(package)
        raw_errata_pkg_nevra = get_nevra(package, clean=False)
        errata_package_names_mapping["raw"][
            clean_errata_pkg_nevra
        ] = raw_errata_pkg_nevra
        errata_packages.add(clean_errata_pkg_nevra)

    missing_packages = errata_packages.difference(albs_records_to_add)
    if missing_packages:
        missing_pkg_names = []
        for missing_pkg in missing_packages:
            full_name = errata_package_names_mapping["raw"][missing_pkg]
            full_albs_name = errata_package_names_mapping["albs"].get(missing_pkg)
            full_name = full_albs_name if full_albs_name else full_name
            missing_pkg_names.append(full_name)
        msg = (
            "Cannot release updateinfo record, the following packages "
            "are missing from platform repositories or have wrong status: "
            + ", ".join(missing_pkg_names)
        )
        raise ValueError(msg)

    tasks = []
    publish_tasks = []
    for repo_href, packages in repo_mapping.items():
        updateinfo_mapping = await prepare_updateinfo_mapping(
            db=db,
            pulp=pulp,
            package_hrefs=[pkg.get_pulp_href() for pkg in packages],
            blacklist_updateinfo=[],
        )
        latest_repo_version = await pulp.get_repo_latest_version(repo_href)
        errata_records = await pulp.list_updateinfo_records(
            id__in=[
                record_id
                for record_id in updateinfo_mapping.keys()
                if record_id == db_record.id
            ],
            repository_version=latest_repo_version,
        )
        with get_pulp_db() as pulp_db:
            append_update_packages_in_update_records(
                pulp_db=pulp_db,
                errata_records=errata_records,
                updateinfo_mapping=updateinfo_mapping,
            )
        tasks.append(
            release_errata_packages(
                db,
                pulp,
                db_record,
                packages,
                db_record.platform,
                repo_href,
            )
        )
        publish_tasks.append(pulp.create_rpm_publication(repo_href))
    await asyncio.gather(*tasks)
    await asyncio.gather(*publish_tasks)
    db_record.release_status = ErrataReleaseStatus.RELEASED
    db_record.last_release_log = "Succesfully released"
    await db.commit()

import asyncio
import collections
import datetime
import logging
import re
import uuid
from contextlib import asynccontextmanager
from typing import Any, Awaitable, DefaultDict, Dict, List, Optional, Tuple

import createrepo_c as cr
import jinja2
from sqlalchemy import and_, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session, load_only, selectinload
from sqlalchemy.sql.expression import func

from alws import models
from alws.config import settings
from alws.constants import (
    ErrataPackageStatus,
    ErrataReferenceType,
    ErrataReleaseStatus,
)
from alws.dependencies import get_db, get_pulp_db
from alws.pulp_models import (
    RpmPackage,
    UpdateCollection,
    UpdatePackage,
    UpdateRecord,
)
from alws.schemas import errata_schema
from alws.schemas.errata_schema import BaseErrataRecord
from alws.utils.errata import (
    clean_errata_title,
    debrand_affected_cpe_list,
    debrand_comment,
    debrand_description_and_title,
    debrand_id,
    debrand_reference,
    get_nevra,
    get_oval_title,
    get_verbose_errata_title,
)
from alws.utils.parsing import clean_release, parse_rpm_nevra
from alws.utils.pulp_client import PulpClient
from alws.utils.pulp_utils import (
    get_rpm_module_packages_from_repository,
    get_rpm_packages_by_ids,
    get_rpm_packages_from_repository,
    get_uuid_from_pulp_href,
)

try:
    # FIXME: ovallib dependency should stay optional
    #        for web-server until we release it.
    from almalinux.liboval.composer import (
        Composer,
        get_object_cls_by_tag,
        get_state_cls_by_tag,
        get_test_cls_by_tag,
        get_variable_cls_by_tag,
    )
    from almalinux.liboval.definition import Definition
    from almalinux.liboval.generator import Generator
    from almalinux.liboval.rpminfo_state import RpminfoState
    from almalinux.liboval.rpminfo_test import RpminfoTest
    from almalinux.liboval.rpmverifyfile_object import RpmverifyfileObject
    from almalinux.liboval.rpmverifyfile_state import RpmverifyfileState
    from almalinux.liboval.rpmverifyfile_test import RpmverifyfileTest
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
            self.parent.criteria["criterion"].append(
                self.criteria["criterion"].pop()
            )
        if (
            len(self.criteria["criteria"]) == 0
            and len(self.criteria["criterion"]) == 0
        ):
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
        timestamp=datetime.datetime.utcnow(),
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
                albs_evra = (
                    f"{albs_pkg.epoch}:{albs_pkg.version}-{albs_pkg.release}"
                )
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
                            if ref.ref_type == ErrataReferenceType.cve
                            and ref.cve
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
            oval.append_object(
                get_variable_cls_by_tag(var["type"]).from_dict(var)
            )
            for obj in record.original_objects:
                if (
                    obj["id"]
                    != var["arithmetic"]["object_component"]["object_ref"]
                ):
                    continue
                if obj["id"] in objects:
                    continue
                objects.add(obj["id"])
                oval.append_object(
                    get_object_cls_by_tag(obj["type"]).from_dict(obj)
                )
    return oval.dump_to_string()


def prepare_search_params(
    errata_record: models.ErrataRecord,
) -> DefaultDict[str, List[str]]:
    search_params = collections.defaultdict(list)
    for package in errata_record.packages:
        for attr in ("name", "version", "epoch"):
            value = str(getattr(package, attr))
            if value in search_params[attr]:
                continue
            search_params[attr].append(value)
    return search_params


async def load_platform_packages(
    platform: models.Platform,
    search_params: DefaultDict[str, List[str]],
    for_release: bool = False,
    module: Optional[str] = None,
) -> Dict[str, Any]:
    cache = {}
    for repo in platform.repos:
        if not repo.production:
            continue

        repo_id = get_uuid_from_pulp_href(repo.pulp_href)
        if module:
            pkgs = get_rpm_module_packages_from_repository(
                repo_id=repo_id,
                module=module,
                pkg_names=search_params["name"],
                pkg_versions=search_params["version"],
                pkg_epochs=search_params["epoch"],
            )
        else:
            pkgs = get_rpm_packages_from_repository(
                repo_id=repo_id,
                pkg_names=search_params["name"],
                pkg_versions=search_params["version"],
                pkg_epochs=search_params["epoch"],
            )

        if not pkgs:
            continue

        for pkg in pkgs:
            if for_release:
                key = pkg.pulp_href
                if not cache.get(key):
                    cache[key] = []
                cache[key].append(repo.pulp_href)
                continue
            short_pkg_name = "-".join(
                (
                    pkg.name,
                    pkg.version,
                    clean_release(pkg.release),
                )
            )
            if not cache.get(short_pkg_name):
                cache[short_pkg_name] = {}
            arch_list = [pkg.arch]
            if pkg.arch == "noarch":
                arch_list = platform.arch_list
            for arch in arch_list:
                if not cache[short_pkg_name].get(arch):
                    cache[short_pkg_name][arch] = []
                if pkg in cache[short_pkg_name][arch]:
                    continue
                cache[short_pkg_name][arch].append(pkg)
    return cache


async def update_errata_record(
    db: AsyncSession,
    update_record: errata_schema.UpdateErrataRequest,
) -> models.ErrataRecord:
    record = await get_errata_record(db, update_record.errata_record_id)
    if update_record.title is not None:
        if update_record.title == record.original_title:
            record.title = None
        else:
            record.title = update_record.title
        if record.title:
            record.oval_title = get_oval_title(
                record.title, record.id, record.severity
            )
    if update_record.description is not None:
        if update_record.description == record.original_description:
            record.description = None
        else:
            record.description = update_record.description
    await db.commit()
    await db.refresh(record)
    return record


async def get_matching_albs_packages(
    db: AsyncSession,
    errata_package: models.ErrataPackage,
    prod_repos_cache,
    module,
) -> List[models.ErrataToALBSPackage]:
    items_to_insert = []
    # We're going to check packages that match name-version-clean_release
    # Note that clean_release doesn't include the .module... str, we match:
    #   - my-pkg-2.0-2
    #   - my-pkg-2.0-20191233git
    #   - etc
    clean_package_name = "-".join(
        (
            errata_package.name,
            errata_package.version,
            clean_release(errata_package.release),
        )
    )
    # We add ErrataToALBSPackage if we find a matching package already
    # in production repositories.
    for prod_package in prod_repos_cache.get(clean_package_name, {}).get(
        errata_package.arch, []
    ):
        mapping = models.ErrataToALBSPackage(
            pulp_href=prod_package.pulp_href,
            status=ErrataPackageStatus.released,
            name=prod_package.name,
            version=prod_package.version,
            release=prod_package.release,
            epoch=int(prod_package.epoch),
            arch=prod_package.arch,
        )
        src_nevra = parse_rpm_nevra(prod_package.rpm_sourcerpm)
        errata_package.source_srpm = src_nevra.name
        items_to_insert.append(mapping)
        errata_package.albs_packages.append(mapping)
        return items_to_insert

    # If we couldn't find any pkg in production repos
    # we'll look for every package that matches name-version
    # inside the ALBS, this is, build_task_artifacts.
    name_query = f"{errata_package.name}-{errata_package.version}"

    query = select(models.BuildTaskArtifact).where(
        and_(
            models.BuildTaskArtifact.type == "rpm",
            models.BuildTaskArtifact.name.startswith(name_query),
        )
    )
    # If the errata record references a module, then we'll get
    # only packages that belong to the right module:stream
    if module:
        module_name, module_stream = module.split(":")
        query = (
            query.join(models.BuildTask)
            .join(models.RpmModule)
            .filter(
                models.RpmModule.name == module_name,
                models.RpmModule.stream == module_stream,
            )
        )

    result = (await db.execute(query)).scalars().all()

    pulp_pkg_ids = [get_uuid_from_pulp_href(pkg.href) for pkg in result]
    pkg_fields = [
        RpmPackage.content_ptr_id,
        RpmPackage.name,
        RpmPackage.epoch,
        RpmPackage.version,
        RpmPackage.release,
        RpmPackage.arch,
        RpmPackage.rpm_sourcerpm,
    ]
    pulp_pkgs = get_rpm_packages_by_ids(pulp_pkg_ids, pkg_fields)
    for package in result:
        pulp_rpm_package = pulp_pkgs.get(package.href)
        if not pulp_rpm_package:
            continue
        clean_pulp_package_name = "-".join(
            (
                pulp_rpm_package.name,
                pulp_rpm_package.version,
                clean_release(pulp_rpm_package.release),
            )
        )
        if (
            pulp_rpm_package.arch not in (errata_package.arch, "noarch")
            or clean_pulp_package_name != clean_package_name
        ):
            continue
        mapping = models.ErrataToALBSPackage(
            albs_artifact_id=package.id,
            status=ErrataPackageStatus.proposal,
            name=pulp_rpm_package.name,
            version=pulp_rpm_package.version,
            release=pulp_rpm_package.release,
            epoch=int(pulp_rpm_package.epoch),
            arch=pulp_rpm_package.arch,
        )
        if errata_package.source_srpm is None:
            nevra = parse_rpm_nevra(pulp_rpm_package.rpm_sourcerpm)
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

    # Rebranding RHEL -> AlmaLinux
    for key in ("description", "title"):
        setattr(
            errata,
            key,
            debrand_description_and_title(getattr(errata, key)),
        )
    alma_errata_id = re.sub(r"^RH", "AL", errata.id)

    # Check if errata refers to a module
    r = re.compile("Module ([\d\w\-\_]+:[\d\.\w]+) is enabled")
    match = r.findall(str(errata.criteria))
    errata_module = None if not match else match[0]

    # Errata db record
    db_errata = models.ErrataRecord(
        id=alma_errata_id,
        freezed=errata.freezed,
        platform_id=errata.platform_id,
        module=errata_module,
        release_status=ErrataReleaseStatus.NOT_RELEASED,
        summary=None,
        solution=None,
        issued_date=errata.issued_date,
        updated_date=errata.updated_date,
        description=None,
        original_description=errata.description,
        title=None,
        oval_title=get_oval_title(
            errata.title, alma_errata_id, errata.severity
        ),
        original_title=get_verbose_errata_title(errata.title, errata.severity),
        contact_mail=platform.contact_mail,
        status=errata.status,
        version=errata.version,
        severity=errata.severity,
        rights=jinja2.Template(platform.copyright).render(
            year=datetime.datetime.utcnow().year
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

    # References
    self_ref_exists = False
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
    if not self_ref_exists:
        html_id = db_errata.id.replace(":", "-")
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

    # Errata Packages
    search_params = prepare_search_params(errata)

    prod_repos_cache = await load_platform_packages(
        platform,
        search_params,
        False,
        db_errata.module,
    )
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
        # Create ErrataToAlbsPackages
        items_to_insert.extend(
            await get_matching_albs_packages(
                db, db_package, prod_repos_cache, db_errata.module
            )
        )

    db.add_all(items_to_insert)
    await db.commit()
    await db.refresh(db_errata)
    return db_errata


async def get_errata_record(
    db: AsyncSession,
    errata_record_id: str,
) -> Optional[models.ErrataRecord]:
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
    errata_ids: Optional[List[str]] = None,
    title: Optional[str] = None,
    platform: Optional[int] = None,
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
        if errata_ids:
            query = query.filter(models.ErrataRecord.id.in_(errata_ids))
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
        "total_records": (
            await db.execute(generate_query(count=True))
        ).scalar(),
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
                    if (
                        albs_pkg.build_id != record.build_id
                        and record_approved
                    ):
                        albs_pkg.status = ErrataPackageStatus.skipped
                    if albs_pkg.build_id == record.build_id:
                        albs_pkg.status = record.status
    return True


async def release_errata_packages(
    session: AsyncSession,
    pulp_client: PulpClient,
    record: models.ErrataRecord,
    packages: List[models.ErrataToALBSPackage],
    platform: models.Platform,
    repo_href: str,
    publish: bool = True,
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
    released_pkgs = set()
    for errata_pkg in packages:
        pulp_pkg = await pulp_client.get_by_href(errata_pkg.get_pulp_href())
        pkg_name_arch = "_".join([pulp_pkg["name"], pulp_pkg["arch"]])
        if errata_pkg.errata_package.reboot_suggested:
            reboot_suggested = True
        if pkg_name_arch in released_pkgs:
            continue
        released_pkgs.add(pkg_name_arch)
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
        if rpm_module or ".module_el" not in pulp_pkg["release"]:
            continue
        query = models.BuildTaskArtifact.href == errata_pkg.pulp_href
        if errata_pkg.albs_artifact_id is not None:
            query = models.BuildTaskArtifact.id == errata_pkg.albs_artifact_id
        db_pkg = await session.execute(
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
                # we use here repository arch, because looking by
                # noarch package (that can be refered to other arch)
                # we can get module with different arch
                "arch": arch,
            }
    collection_name = (
        f"{platform.name.lower()}-for-{arch}-{repo_stage}-"
        f"rpms__{platform_version}_default"
    )
    default_summary = clean_errata_title(
        record.get_title(), severity=record.severity
    )
    pulp_record = {
        "id": record.id,
        "updated_date": datetime.datetime.utcnow().strftime(
            "%Y-%m-%d %H:%M:%S"
        ),
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
    if publish:
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
                        selectinload(
                            models.BuildTaskArtifact.build_task
                        ).selectinload(models.BuildTask.rpm_module)
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
                        models.ErrataToALBSPackage.albs_artifact_id
                        == db_pkg.id,
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
        str,
        List[
            Tuple[models.BuildTaskArtifact, dict, models.ErrataToALBSPackage]
        ],
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
                pulp_record.updated_date = datetime.datetime.utcnow().strftime(
                    "%Y-%m-%d %H:%M:%S"
                )


def get_albs_packages_from_record(
    record: models.ErrataRecord,
    pulp_packages: Dict[str, Any],
) -> DefaultDict[str, List[models.ErrataToALBSPackage]]:
    repo_mapping = collections.defaultdict(list)
    errata_packages = set()
    albs_packages = set()
    pkg_names_mapping = {
        "raw": {},
        "albs": {},
    }
    for package in record.packages:
        clean_pkg_nevra = get_nevra(package)
        raw_pkg_nevra = get_nevra(package, clean=False)
        pkg_names_mapping["raw"][clean_pkg_nevra] = raw_pkg_nevra
        errata_packages.add(clean_pkg_nevra)
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
                clean_pkg_nevra = get_nevra(
                    albs_package,
                    arch=albs_package.errata_package.arch,
                )
                raw_pkg_nevra = get_nevra(albs_package, clean=False)
                albs_packages.add(clean_pkg_nevra)
                pkg_names_mapping["albs"][clean_pkg_nevra] = raw_pkg_nevra

    missing_packages = errata_packages.difference(albs_packages)
    if missing_packages:
        missing_pkg_names = []
        for missing_pkg in missing_packages:
            full_name = pkg_names_mapping["raw"][missing_pkg]
            full_albs_name = pkg_names_mapping["albs"].get(missing_pkg)
            full_name = full_albs_name if full_albs_name else full_name
            missing_pkg_names.append(full_name)
        msg = (
            "Cannot release updateinfo record, the following packages "
            "are missing from platform repositories or have wrong status: "
            + ", ".join(missing_pkg_names)
        )
        raise ValueError(msg)
    return repo_mapping


async def process_errata_release_for_repos(
    db_record: models.ErrataRecord,
    repo_mapping: DefaultDict[str, List[models.ErrataToALBSPackage]],
    session: AsyncSession,
    pulp: PulpClient,
    publish: bool = True,
) -> Optional[List[Awaitable]]:
    release_tasks = []
    publish_tasks = []
    for repo_href, packages in repo_mapping.items():
        pkg_hrefs = []
        for pkg in packages:
            pkg.status = ErrataPackageStatus.released
            pkg_hrefs.append(pkg.get_pulp_href())
        updateinfo_mapping = await prepare_updateinfo_mapping(
            db=session,
            pulp=pulp,
            package_hrefs=pkg_hrefs,
            blacklist_updateinfo=[],
        )
        latest_repo_version = await pulp.get_repo_latest_version(repo_href)
        if latest_repo_version:
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
        release_tasks.append(
            release_errata_packages(
                session,
                pulp,
                db_record,
                packages,
                db_record.platform,
                repo_href,
                publish=publish,
            )
        )
        if publish:
            publish_tasks.append(pulp.create_rpm_publication(repo_href))
    if not publish:
        return release_tasks
    await asyncio.gather(*release_tasks)
    await asyncio.gather(*publish_tasks)


def generate_query_for_release(records_ids: List[str]):
    query = (
        select(models.ErrataRecord)
        .where(models.ErrataRecord.id.in_(records_ids))
        .options(
            selectinload(models.ErrataRecord.references),
            selectinload(models.ErrataRecord.packages)
            .selectinload(models.ErrataPackage.albs_packages)
            .selectinload(models.ErrataToALBSPackage.build_artifact),
            selectinload(models.ErrataRecord.platform).selectinload(
                models.Platform.repos
            ),
        )
        .with_for_update()
    )
    return query


async def get_release_logs(
    record_id: str,
    pulp_packages: dict,
    session: AsyncSession,
    repo_mapping: dict,
    db_record: list,
) -> str:
    release_log = [
        f"Record {record_id} successfully released at {datetime.datetime.utcnow()}\n"
    ]
    pkg_fields = [
        RpmPackage.name,
        RpmPackage.epoch,
        RpmPackage.version,
        RpmPackage.release,
        RpmPackage.arch,
    ]
    pulp_pkgs = get_rpm_packages_by_ids(
        pulp_pkg_ids=[get_uuid_from_pulp_href(pkg) for pkg in pulp_packages],
        pkg_fields=pkg_fields,
    )
    arches = set()
    pkgs = []
    for pkg in pulp_pkgs:
        arches.add(pulp_pkgs[pkg].arch)
        pkgs.append(pulp_pkgs[pkg].nevra)

    repositories = await session.execute(
        select(models.Repository).where(
            models.Repository.pulp_href.in_(repo_mapping),
        )
    )
    repositories: List[models.Repository] = repositories.scalars().all()

    if db_record.module:
        release_log.append(f"Module: {db_record.module}\n")

    release_log.extend(
        [
            "Architecture(s): " + ", ".join(arches),
            "\nPackages:\n" + "\n".join(pkgs),
            "\nRepositories:\n"
            + "\n".join([repo.url for repo in repositories]),
        ]
    )
    return "".join(release_log)


async def release_errata_record(record_id: str):
    pulp = PulpClient(
        settings.pulp_host,
        settings.pulp_user,
        settings.pulp_password,
    )
    async with asynccontextmanager(get_db)() as session:
        session: AsyncSession
        db_record = await session.execute(
            generate_query_for_release([record_id]),
        )
        db_record: Optional[models.ErrataRecord] = db_record.scalars().first()
        if not db_record:
            logging.info("Record with %s id doesn't exists", record_id)
            return

        logging.info("Record release %s has been started", record_id)
        search_params = prepare_search_params(db_record)
        pulp_packages = await load_platform_packages(
            db_record.platform,
            search_params,
            for_release=True,
        )
        try:
            repo_mapping = get_albs_packages_from_record(
                db_record, pulp_packages
            )
        except Exception as exc:
            db_record.release_status = ErrataReleaseStatus.FAILED
            db_record.last_release_log = str(exc)
            logging.exception("Cannot release %s record:", record_id)
            await session.commit()
            return

        await process_errata_release_for_repos(
            db_record,
            repo_mapping,
            session,
            pulp,
        )
        db_record.release_status = ErrataReleaseStatus.RELEASED

        db_record.last_release_log = await get_release_logs(
            record_id=record_id,
            pulp_packages=pulp_packages,
            session=session,
            repo_mapping=repo_mapping,
            db_record=db_record,
        )
        await session.commit()
    logging.info("Record %s successfully released", record_id)


async def bulk_errata_records_release(records_ids: List[str]):
    pulp = PulpClient(
        settings.pulp_host,
        settings.pulp_user,
        settings.pulp_password,
    )
    release_tasks = []
    repos_to_publish = []
    async with asynccontextmanager(get_db)() as session:
        await session.execute(
            update(models.ErrataRecord)
            .where(models.ErrataRecord.id.in_(records_ids))
            .values(
                release_status=ErrataReleaseStatus.IN_PROGRESS,
                last_release_log=None,
            )
        )
        await session.commit()

    async with asynccontextmanager(get_db)() as session:
        session: AsyncSession
        db_records = await session.execute(
            generate_query_for_release(records_ids),
        )
        db_records: List[models.ErrataRecord] = db_records.scalars().all()
        if not db_records:
            logging.info(
                "Cannot find records by the following ids: %s",
                records_ids,
            )
            return

        logging.info(
            "Starting bulk errata release, the following records are locked: %s",
            [rec.id for rec in db_records],
        )
        for db_record in db_records:
            logging.info("Preparing data for %s", db_record.id)
            search_params = prepare_search_params(db_record)
            pulp_packages = await load_platform_packages(
                db_record.platform,
                search_params,
                for_release=True,
            )
            try:
                repo_mapping = get_albs_packages_from_record(
                    db_record, pulp_packages
                )
            except Exception as exc:
                db_record.release_status = ErrataReleaseStatus.FAILED
                db_record.last_release_log = str(exc)
                logging.exception("Cannot prepare data for %s:", db_record.id)
                continue

            tasks = await process_errata_release_for_repos(
                db_record,
                repo_mapping,
                session,
                pulp,
                publish=False,
            )
            db_record.release_status = ErrataReleaseStatus.RELEASED
            db_record.last_release_log = await get_release_logs(
                record_id=db_record.id,
                pulp_packages=pulp_packages,
                session=session,
                repo_mapping=repo_mapping,
                db_record=db_record,
            )
            if not tasks:
                continue
            repos_to_publish.extend(repo_mapping.keys())
            release_tasks.extend(tasks)
        await session.commit()
    logging.info("Executing release tasks")
    await asyncio.gather(*release_tasks)
    logging.info("Executing publication tasks")
    await asyncio.gather(
        *(pulp.create_rpm_publication(href) for href in set(repos_to_publish))
    )
    logging.info("Bulk errata release is finished")


async def get_updateinfo_xml_from_pulp(
    record_id: str,
) -> Optional[str]:
    pulp_client = PulpClient(
        settings.pulp_host,
        settings.pulp_user,
        settings.pulp_password,
    )
    errata_records = await pulp_client.list_updateinfo_records(
        id__in=[record_id],
    )
    if not errata_records:
        return
    cr_upd = cr.UpdateInfo()
    for errata_record in errata_records:
        cr_ref = cr.UpdateReference()
        cr_rec = cr.UpdateRecord()
        cr_col = cr.UpdateCollection()
        cr_mod = cr.UpdateCollectionModule()
        cr_rec.id = errata_record["id"]
        for key in (
            "issued_date",
            "pushcount",
            "release",
            "rights",
            "severity",
            "summary",
            "title",
            "description",
            "fromstr",
            "type",
            "status",
            "version",
            "rights",
            "updated_date",
        ):
            if key not in errata_record:
                continue
            value = errata_record[key]
            if key in (
                "issued_date",
                "updated_date",
            ):
                value = datetime.datetime.fromisoformat(value)
            setattr(cr_rec, key, value)
        for ref in errata_record.get("references", []):
            cr_ref.href = ref["href"]
            cr_ref.type = ref["type"]
            cr_ref.id = ref["id"]
            cr_ref.title = ref["title"]
            cr_rec.append_reference(cr_ref)
        collection = errata_record["pkglist"][0]
        cr_col.name = collection["name"]
        cr_col.shortname = collection["shortname"]
        if collection["module"]:
            for key in (
                "stream",
                "name",
                "version",
                "arch",
                "context",
            ):
                setattr(cr_mod, key, collection["module"][key])
            cr_col.module = cr_mod
        for package in collection["packages"]:
            cr_pkg = cr.UpdateCollectionPackage()
            for key in (
                "name",
                "src",
                "version",
                "release",
                "arch",
                "filename",
                "sum",
                "epoch",
                "reboot_suggested",
            ):
                if key not in package:
                    continue
                setattr(cr_pkg, key, package[key])
            if package["sum_type"] == "sha256":
                cr_pkg.sum_type = cr.SHA256
            else:
                cr_pkg.sum_type = package["sum_type"]
            cr_col.append(cr_pkg)
        cr_rec.append_collection(cr_col)
        cr_upd.append(cr_rec)
    return cr_upd.xml_dump()

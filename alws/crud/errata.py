import asyncio
import collections
import datetime
import json
import logging
import re
import uuid
from typing import (
    Any,
    Awaitable,
    DefaultDict,
    Dict,
    List,
    Optional,
    Tuple,
    Union,
)

import aioredis
import createrepo_c as cr
import jinja2
from fastapi_sqla import open_async_session, open_session
from sqlalchemy import and_, delete, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session, load_only, selectinload
from sqlalchemy.sql.expression import func

from alws import models
from alws.config import settings
from alws.constants import (
    ErrataPackageStatus,
    ErrataPackagesType,
    ErrataReferenceType,
    ErrataReleaseStatus,
)
from alws.dependencies import get_async_db_key
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
from alws.utils.github_integration_helper import (
    close_issues,
    create_github_issue,
    get_github_client,
)
from alws.utils.oval_add_al8_gpg_keys import add_multiple_gpg_keys_to_oval
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
    from almalinux.liboval.data_generation import (
        Module,
        OvalDataGenerator,
        Platform,
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


async def get_oval_xml(
    db: AsyncSession, platform_name: str, only_released: bool = False
):
    query = select(models.NewErrataRecord).options(
        selectinload(models.NewErrataRecord.packages)
        .selectinload(models.NewErrataPackage.albs_packages)
        .selectinload(models.NewErrataToALBSPackage.build_artifact)
        .selectinload(models.BuildTaskArtifact.build_task),
        selectinload(models.NewErrataRecord.references).selectinload(
            models.NewErrataReference.cve
        ),
    )

    platform = await db.execute(
        select(models.Platform).where(models.Platform.name == platform_name)
    )
    platform: models.Platform = platform.scalars().first()

    if not platform:
        return

    query = query.filter(models.NewErrataRecord.platform_id == platform.id)

    if only_released:
        query = query.filter(
            models.NewErrataRecord.release_status
            == ErrataReleaseStatus.RELEASED
        )

    records = (await db.execute(query)).scalars().all()
    return errata_records_to_oval(records, platform_name)


async def get_new_oval_xml(
    db: AsyncSession, platform_name: str, only_released: bool = False
):
    platform_subq = (
        select(models.Platform.id).where(models.Platform.name == platform_name)
    ).scalar_subquery()

    query = (
        select(models.NewErrataRecord)
        .where(models.NewErrataRecord.platform_id == platform_subq)
        .options(
            selectinload(models.NewErrataRecord.packages)
            .selectinload(models.NewErrataPackage.albs_packages)
            .selectinload(models.NewErrataToALBSPackage.build_artifact)
            .selectinload(models.BuildTaskArtifact.build_task),
            selectinload(models.NewErrataRecord.references).selectinload(
                models.NewErrataReference.cve
            ),
        )
    )

    if only_released:
        query = query.filter(
            models.NewErrataRecord.release_status
            == ErrataReleaseStatus.RELEASED
        )

    records = (await db.execute(query)).scalars().all()
    return new_errata_records_to_oval(records)


def add_oval_objects(new_objects, objects, oval, get_cls_by_tag_func):
    for new_obj in new_objects:
        if new_obj["id"] not in objects:
            objects.add(new_obj["id"])
            oval.append_object(
                get_cls_by_tag_func(new_obj["type"]).from_dict(new_obj)
            )


def new_errata_records_to_oval(records: List[models.NewErrataRecord]):
    oval = Composer()
    generator = Generator(
        product_name="AlmaLinux OS Errata System",
        product_version="0.0.1",
        schema_version="5.10",
        timestamp=datetime.datetime.utcnow(),
    )
    oval.generator = generator
    objects = set()
    for record in records:
        if not record.criteria:
            logging.warning(
                "Skipping OVAL XML generation of %s. Reason: Missing OVAL data",
                record.id,
            )
            continue
        title = record.oval_title
        definition = Definition.from_dict({
            "id": record.definition_id,
            "version": record.definition_version,
            "class": record.definition_class,
            "metadata": {
                "title": title,
                "description": (
                    record.description
                    if record.description
                    else record.original_description
                ),
                "advisory": {
                    "from": record.contact_mail,
                    "severity": record.severity.capitalize(),
                    "rights": record.rights,
                    "issued_date": record.issued_date,
                    "updated_date": record.updated_date,
                    "affected_cpe_list": record.affected_cpe,
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
                            "impact": ref.cve.impact.capitalize(),
                            "cwe": ref.cve.cwe,
                            "cvss3": ref.cve.cvss3,
                        }
                        for ref in record.references
                        if ref.ref_type == ErrataReferenceType.cve and ref.cve
                    ],
                },
                # TODO: It would be great if we update the ErrataReferenceTypes
                # in a way that we use the same way through all the involved
                # code. We only need to take care of those using "self_ref",
                # which I propose to move its value to "alsa". Then, here we
                # can use the ErrataReferenceType value in capital letters and
                # get rid of this.
                "references": [
                    {
                        "id": ref.ref_id,
                        "url": ref.href,
                        "source": (
                            "RHSA"
                            if ref.ref_type == ErrataReferenceType.rhsa
                            else (
                                "CVE"
                                if ref.ref_type == ErrataReferenceType.cve
                                else "ALSA"
                            )
                        ),
                    }
                    for ref in record.references
                    if ref.ref_type
                    in [
                        ErrataReferenceType.self_ref,
                        ErrataReferenceType.rhsa,
                        ErrataReferenceType.cve,
                    ]
                ],
            },
            "criteria": record.criteria,
        })
        oval.append_object(definition)

        for new_oval_objects, get_cls_by_tag_func in (
            (record.tests, get_test_cls_by_tag),
            (record.objects, get_object_cls_by_tag),
            (record.states, get_state_cls_by_tag),
            (record.variables, get_variable_cls_by_tag),
        ):
            if new_oval_objects is None:
                continue
            add_oval_objects(
                new_oval_objects,
                objects,
                oval,
                get_cls_by_tag_func,
            )

    return oval.dump_to_string()


def errata_records_to_oval(
    records: List[models.NewErrataRecord], platform_name: str
):
    oval = Composer()
    generator = Generator(
        product_name="AlmaLinux OS Errata System",
        product_version="0.0.1",
        schema_version="5.10",
        timestamp=datetime.datetime.utcnow(),
    )
    oval.generator = generator
    gpg_keys = {
        "8": "2AE81E8ACED7258B",
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
        definition = Definition.from_dict({
            "id": debrand_id(record.definition_id),
            "version": record.definition_version,
            "class": record.definition_class,
            "metadata": {
                "title": title,
                "description": (
                    record.description
                    if record.description
                    else record.original_description
                ),
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
        })
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
            if state_cls == RpminfoState and state["signature_keyid"]:
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
    # Almalinux8 have multiple GPG keys.
    # https://almalinux.org/blog/2023-12-20-almalinux-8-key-update/
    # So this platfrom requires additional oval processing
    if platform_name.lower() == 'almalinux-8':
        oval = add_multiple_gpg_keys_to_oval(oval)
    return oval.dump_to_string()


def prepare_search_params(
    errata_record: Union[models.NewErrataRecord, BaseErrataRecord],
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
            # We do not need to map src pkgs
            if pkg.arch == "src":
                continue

            if for_release:
                key = pkg.pulp_href
                if not cache.get(key):
                    cache[key] = []
                cache[key].append(repo.pulp_href)
                continue
            short_pkg_name = "-".join((
                pkg.name,
                pkg.version,
                clean_release(pkg.release),
            ))
            if not cache.get(short_pkg_name):
                cache[short_pkg_name] = {}
            arch_list = [pkg.arch]
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
) -> models.NewErrataRecord:
    record = await get_errata_record(
        db,
        update_record.errata_record_id,
        update_record.errata_platform_id,
    )
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
    await db.flush()
    await db.refresh(record)
    return record


async def get_matching_albs_packages(
    db: AsyncSession,
    errata_package: models.NewErrataPackage,
    prod_repos_cache,
    module,
) -> Tuple[List[models.NewErrataToALBSPackage], dict]:
    package_type = {}
    items_to_insert = []
    # We're going to check packages that match name-version-clean_release
    # Note that clean_release doesn't include the .module... str, we match:
    #   - my-pkg-2.0-2
    #   - my-pkg-2.0-20191233git
    #   - etc
    clean_package_name = "-".join((
        errata_package.name,
        errata_package.version,
        clean_release(errata_package.release),
    ))
    # We add ErrataToALBSPackage if we find a matching package already
    # in production repositories.
    for prod_package in prod_repos_cache.get(clean_package_name, {}).get(
        errata_package.arch, []
    ):
        # src and some noarch packages are coming with an empty rpm_sourcerpm,
        # field which makes parse_rpm_nevra(prod_package.rpm_sourcerpm) below
        # to fail.
        if not prod_package.rpm_sourcerpm:
            logging.warning(
                "Skipping '%s' with empty sourcerpm field in pulp href '%s'",
                prod_package.name,
                prod_package.pulp_href,
            )
            continue
        mapping = models.NewErrataToALBSPackage(
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
        package_type["type"] = ErrataPackagesType.PROD
        return items_to_insert, package_type

    # If we couldn't find any pkg in production repos
    # we'll look for every package that matches name-version
    # inside the ALBS, this is, build_task_artifacts.
    name_query = f"{errata_package.name}-{errata_package.version}"

    query = (
        select(models.BuildTaskArtifact)
        .where(
            and_(
                models.BuildTaskArtifact.type == "rpm",
                models.BuildTaskArtifact.name.startswith(name_query),
            )
        )
        .options(
            selectinload(models.BuildTaskArtifact.build_task),
        )
    )
    # If the errata record references a module, then we'll get
    # only packages that belong to the right module:stream
    if module:
        module_name, module_stream = module.split(":")
        query = (
            query.join(models.BuildTaskArtifact.build_task)
            .join(models.BuildTask.rpm_modules)
            .filter(
                models.RpmModule.name == module_name,
                models.RpmModule.stream == module_stream,
            )
        )

    result = (await db.execute(query)).scalars().all()

    pulp_pkg_ids = []
    build_ids = set()
    for pkg in result:
        pulp_pkg_ids.append(get_uuid_from_pulp_href(pkg.href))
        build_ids.add(pkg.build_task.build_id)
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
    errata_record_ids = set()
    for package in result:
        pulp_rpm_package = pulp_pkgs.get(package.href)
        if not pulp_rpm_package:
            continue
        clean_pulp_package_name = "-".join((
            pulp_rpm_package.name,
            pulp_rpm_package.version,
            clean_release(pulp_rpm_package.release),
        ))
        if (
            pulp_rpm_package.arch not in (errata_package.arch, "noarch")
            or clean_pulp_package_name != clean_package_name
        ):
            continue
        mapping = models.NewErrataToALBSPackage(
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
        errata_record_ids.add(errata_package.errata_record_id)
    package_type = {
        "type": ErrataPackagesType.BUILD,
        "build_ids": list(build_ids),
    }
    return items_to_insert, package_type


async def process_new_errata_references(
    db: AsyncSession,
    errata: BaseErrataRecord,
    db_errata: models.NewErrataRecord,
    platform: models.Platform,
):
    references = []
    self_ref_exists = False

    db_cves = collections.defaultdict()
    cve_ids = [ref.cve.id for ref in errata.references if ref.cve]
    if cve_ids:
        db_cves = {
            cve.id: cve
            for cve in (
                await db.execute(
                    select(models.ErrataCVE).where(
                        models.ErrataCVE.id.in_(cve_ids)
                    )
                )
            )
            .scalars()
            .all()
        }

    for ref in errata.references:
        db_cve = None
        if ref.cve:
            db_cve = db_cves.get(ref.cve.id)
            if db_cve is None:
                db_cve = models.ErrataCVE(
                    id=ref.cve.id,
                    cvss3=ref.cve.cvss3,
                    cwe=ref.cve.cwe,
                    impact=ref.cve.impact,
                    public=ref.cve.public,
                )
                references.append(db_cve)
        ref_title = ""
        if ref.ref_type in (
            ErrataReferenceType.cve.value,
            ErrataReferenceType.rhsa.value,
        ):
            ref_title = ref.ref_id
        db_reference = models.NewErrataReference(
            href=ref.href,
            ref_id=ref.ref_id,
            ref_type=ref.ref_type,
            title=ref_title,
            cve=db_cve,
        )
        if ref.ref_type == ErrataReferenceType.self_ref.value:
            self_ref_exists = True
        db_errata.references.append(db_reference)
        references.append(db_reference)

    if not self_ref_exists:
        html_id = db_errata.id.replace(":", "-")
        self_ref = models.NewErrataReference(
            href=(
                "https://errata.almalinux.org/"
                f"{platform.distr_version}/{html_id}.html"
            ),
            ref_id=db_errata.id,
            ref_type=ErrataReferenceType.self_ref,
            title=db_errata.id,
        )
        db_errata.references.append(self_ref)
        references.append(self_ref)
    return references


async def process_new_errata_packages(
    db: AsyncSession,
    errata: BaseErrataRecord,
    db_errata: models.NewErrataRecord,
    platform: models.Platform,
):
    packages = []
    pkg_types = []
    search_params = prepare_search_params(errata)
    prod_repos_cache = await load_platform_packages(
        platform,
        search_params,
        False,
        db_errata.module,
    )
    for package in errata.packages:
        # Just in case
        if package.arch == "src":
            continue
        db_package = models.NewErrataPackage(
            name=package.name,
            version=package.version,
            release=package.release,
            epoch=package.epoch,
            arch=package.arch,
            # TODO: Consider providing source_srpm, if can be of any help
            source_srpm=None,
            reboot_suggested=False,
        )
        db_errata.packages.append(db_package)
        packages.append(db_package)
        # Create ErrataToAlbsPackages
        matching_packages, pkg_type = await get_matching_albs_packages(
            db, db_package, prod_repos_cache, db_errata.module
        )
        packages.extend(matching_packages)
        pkg_types.append(pkg_type)
    return packages, pkg_types


async def create_new_errata_record(db: AsyncSession, errata: BaseErrataRecord):
    platform = await db.execute(
        select(models.Platform)
        .where(models.Platform.id == errata.platform_id)
        .options(selectinload(models.Platform.repos))
    )
    platform = platform.scalars().first()
    items_to_insert = []
    original_id = errata.id
    oval_title = f"{errata.id}: {errata.title} ({errata.severity.capitalize()})"

    # Errata db record
    db_errata = models.NewErrataRecord(
        id=errata.id,
        freezed=errata.freezed,
        platform_id=errata.platform_id,
        module=errata.module,
        release_status=ErrataReleaseStatus.NOT_RELEASED,
        # TODO: Not sure it's used, check and if not, remove from data model
        summary=None,
        # TODO: Not used AFAIK, maybe can be removed from data model
        solution=None,
        issued_date=errata.issued_date,
        updated_date=errata.updated_date,
        description=None,
        original_description=errata.description,
        title=None,
        oval_title=oval_title,
        # TODO: I'd prefer to keep the title without severity, and then present
        # the severity differently in UI
        original_title=f"{errata.severity.capitalize()}: {errata.title}",
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
        # TODO: Right now we're adding all repos cpes
        # Ideally, we should generate affected cpes based on the repos
        # where the affected packages live.
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
    items_to_insert.extend(
        await process_new_errata_references(db, errata, db_errata, platform)
    )
    # Errata Packages
    new_errata_packages, pkg_types = (
        await process_new_errata_packages(db, errata, db_errata, platform)
    )
    items_to_insert.extend(new_errata_packages)

    db.add_all(items_to_insert)
    await db.flush()
    await db.refresh(db_errata)
    if not settings.github_integration_enabled:
        return db_errata

    try:
        github_client = await get_github_client()
        await create_github_issue(
            client=github_client,
            title=errata.title,
            description=errata.description,
            advisory_id=errata.id,
            original_id=original_id,
            platform_name=platform.name,
            severity=errata.severity,
            packages=errata.packages,
            platform_id=errata.platform_id,
            find_packages_types=pkg_types,
        )
    except Exception as err:
        logging.exception(
            "Cannot create GitHub issue: %s",
            err,
        )
    return db_errata


async def create_errata_record(db: AsyncSession, errata: BaseErrataRecord):
    platform = await db.execute(
        select(models.Platform)
        .where(models.Platform.id == errata.platform_id)
        .options(selectinload(models.Platform.repos))
    )
    platform = platform.scalars().first()
    items_to_insert = []
    original_id = errata.id

    # Rebranding RHEL -> AlmaLinux
    for key in ("description", "title"):
        setattr(
            errata,
            key,
            debrand_description_and_title(getattr(errata, key)),
        )
    alma_errata_id = re.sub(r"^RH", "AL", errata.id)

    # Check if errata refers to a module
    r = re.compile(r"Module ([\d\w\-\_]+:[\d\.\w]+) is enabled")
    match = r.findall(str(errata.criteria))
    # Ensure we get a module and is not the -devel one
    errata_module = None if not match else match[0].replace("-devel:", ":")

    # Errata db record
    db_errata = models.NewErrataRecord(
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
        db_reference = models.NewErrataReference(
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
        self_ref = models.NewErrataReference(
            href=(
                "https://errata.almalinux.org/"
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
    pkg_types = []
    for package in errata.packages:
        db_package = models.NewErrataPackage(
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
        matching_packages, pkg_type = await get_matching_albs_packages(
            db, db_package, prod_repos_cache, db_errata.module
        )
        pkg_types.append(pkg_type)
        items_to_insert.extend(matching_packages)

    db.add_all(items_to_insert)
    await db.flush()
    await db.refresh(db_errata)
    if not settings.github_integration_enabled:
        return db_errata

    try:
        github_client = await get_github_client()
        await create_github_issue(
            client=github_client,
            title=errata.title,
            description=errata.description,
            advisory_id=alma_errata_id,
            original_id=original_id,
            platform_name=platform.name,
            severity=errata.severity,
            packages=errata.packages,
            platform_id=errata.platform_id,
            find_packages_types=pkg_types,
        )
    except Exception as err:
        logging.exception(
            "Cannot create GitHub issue: %s",
            err,
        )
    return db_errata


async def get_errata_record(
    db: AsyncSession,
    errata_record_id: str,
    errata_platform_id: int,
) -> Optional[models.NewErrataRecord]:
    options = [
        selectinload(models.NewErrataRecord.packages)
        .selectinload(models.NewErrataPackage.albs_packages)
        .selectinload(models.NewErrataToALBSPackage.build_artifact)
        .selectinload(models.BuildTaskArtifact.build_task),
        selectinload(models.NewErrataRecord.references).selectinload(
            models.NewErrataReference.cve
        ),
    ]
    query = (
        select(models.NewErrataRecord)
        .options(*options)
        .order_by(models.NewErrataRecord.updated_date.desc())
        .where(
            models.NewErrataRecord.id == errata_record_id,
            models.NewErrataRecord.platform_id == errata_platform_id,
        )
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
            load_only(
                models.NewErrataRecord.id,
                models.NewErrataRecord.updated_date,
                models.NewErrataRecord.platform_id,
            )
        )
    else:
        options.extend([
            selectinload(models.NewErrataRecord.packages)
            .selectinload(models.NewErrataPackage.albs_packages)
            .selectinload(models.NewErrataToALBSPackage.build_artifact)
            .selectinload(models.BuildTaskArtifact.build_task),
            selectinload(models.NewErrataRecord.references).selectinload(
                models.NewErrataReference.cve
            ),
        ])

    def generate_query(count=False):
        query = select(func.count(models.NewErrataRecord.id))
        if not count:
            query = select(models.NewErrataRecord).options(*options)
            query = query.order_by(models.NewErrataRecord.id.desc())
        if errata_id:
            query = query.filter(
                models.NewErrataRecord.id.like(f"%{errata_id}%")
            )
        if errata_ids:
            query = query.filter(models.NewErrataRecord.id.in_(errata_ids))
        if title:
            query = query.filter(
                or_(
                    models.NewErrataRecord.title.like(f"%{title}%"),
                    models.NewErrataRecord.original_title.like(f"%{title}%"),
                )
            )
        if platform:
            query = query.filter(models.NewErrataRecord.platform_id == platform)
        if cve_id:
            query = query.filter(
                models.NewErrataRecord.cves.like(f"%{cve_id}%")
            )
        if status:
            query = query.filter(
                models.NewErrataRecord.release_status == status
            )
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
    for record in request:
        errata_record = await db.execute(
            select(models.NewErrataRecord)
            .where(
                models.NewErrataRecord.id == record.errata_record_id,
                models.NewErrataRecord.platform_id == record.errata_platform_id,
            )
            .options(
                selectinload(models.NewErrataRecord.packages)
                .selectinload(models.NewErrataPackage.albs_packages)
                .selectinload(models.NewErrataToALBSPackage.build_artifact)
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
                        "There is already released package "
                        f"with same source: {albs_pkg}"
                    )
                if albs_pkg.build_id != record.build_id and record_approved:
                    albs_pkg.status = ErrataPackageStatus.skipped
                if albs_pkg.build_id == record.build_id:
                    albs_pkg.status = record.status
    await db.flush()
    return True


async def release_errata_packages(
    session: AsyncSession,
    pulp_client: PulpClient,
    record: models.NewErrataRecord,
    packages: List[models.NewErrataToALBSPackage],
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
        dict_packages.append({
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
        })
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
                    models.BuildTask.rpm_modules
                )
            )
        )
        db_pkg = db_pkg.scalars().first()
        if not db_pkg:
            continue
        db_module = next(
            (
                i
                for i in db_pkg.build_task.rpm_modules
                if '-devel' not in i.name
            ),
            None,
        )
        if db_module is not None:
            rpm_module = {
                "name": db_module.name,
                "stream": db_module.stream,
                "version": int(db_module.version),
                "context": db_module.context,
                # we use here repository arch, because looking by
                # noarch package (that can be referred to other arch)
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
        "pkglist": [{
            "name": collection_name,
            "short": collection_name,
            "module": rpm_module,
            "packages": dict_packages,
        }],
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
    logging.info(
        'Adding the "%s" record to the "%s" repo',
        record.id,
        repo_href,
    )
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
    List[Tuple[models.BuildTaskArtifact, dict, models.NewErrataToALBSPackage]],
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
                        ).selectinload(models.BuildTask.rpm_modules)
                    )
                )
            )
            .scalars()
            .all()
        )
        for db_pkg in db_pkg_list:
            errata_pkgs = await db.execute(
                select(models.NewErrataToALBSPackage)
                .where(
                    or_(
                        models.NewErrataToALBSPackage.albs_artifact_id
                        == db_pkg.id,
                        models.NewErrataToALBSPackage.pulp_href == pkg_href,
                    )
                )
                .options(
                    selectinload(models.NewErrataToALBSPackage.errata_package),
                    selectinload(models.NewErrataToALBSPackage.build_artifact),
                )
            )
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
            for errata_pkg in errata_pkgs.scalars().all():
                errata_id = errata_pkg.errata_package.errata_record_id
                if errata_id in blacklist_updateinfo:
                    continue
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
            Tuple[models.BuildTaskArtifact, dict, models.NewErrataToALBSPackage]
        ],
    ],
):
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
            pulp_db.flush()


def get_albs_packages_from_record(
    record: models.NewErrataRecord,
    pulp_packages: Dict[str, Any],
    force: bool = False,
) -> Tuple[DefaultDict[str, List[models.NewErrataToALBSPackage]], List[str]]:
    repo_mapping = collections.defaultdict(list)
    errata_packages = set()
    albs_packages = set()
    missing_pkg_names = []
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
        for missing_pkg in missing_packages:
            full_name = pkg_names_mapping["raw"][missing_pkg]
            full_albs_name = pkg_names_mapping["albs"].get(missing_pkg)
            full_name = full_albs_name if full_albs_name else full_name
            missing_pkg_names.append(full_name)
        msg = (
            "Cannot release updateinfo record, the following packages "
            "are missing from platform repositories or have wrong status:\n"
            + ",\n".join(missing_pkg_names)
        )
        if not force:
            raise ValueError(msg)
    return repo_mapping, missing_pkg_names


async def process_errata_release_for_repos(
    db_record: models.NewErrataRecord,
    repo_mapping: DefaultDict[str, List[models.NewErrataToALBSPackage]],
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
        logging.info("Preparing udpateinfo mapping")
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
            logging.info("Appending packages to existing errata records")
            with open_session(key="pulp") as pulp_db:
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
                publish=False,
            )
        )
        if publish:
            publish_tasks.append(
                pulp.create_rpm_publication(repo_href, sleep_time=30.0)
            )
    if not publish:
        return release_tasks
    logging.info("Releasing errata packages in async tasks")
    await asyncio.gather(*release_tasks)
    logging.info("Publicating repositories in async tasks")
    await asyncio.gather(*publish_tasks)


def generate_query_for_release(records_ids: List[str]):
    query = (
        select(models.NewErrataRecord)
        .where(models.NewErrataRecord.id.in_(records_ids))
        .options(
            selectinload(models.NewErrataRecord.references),
            selectinload(models.NewErrataRecord.packages)
            .selectinload(models.NewErrataPackage.albs_packages)
            .selectinload(models.NewErrataToALBSPackage.build_artifact),
            selectinload(models.NewErrataRecord.platform).selectinload(
                models.Platform.repos
            ),
        )
        .with_for_update()
    )
    return query


# TODO: Check db_record
async def get_release_logs(
    record_id: str,
    pulp_packages: dict,
    session: AsyncSession,
    repo_mapping: dict,
    db_record: list,
    force_flag: bool,
    missing_pkg_names: List[str],
) -> str:
    release_log = [
        f"Record {record_id} successfully released at"
        f" {datetime.datetime.utcnow()}\n"
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
    for pkg in pulp_pkgs.values():
        arches.add(pkg.arch)
        pkgs.append(pkg.nevra)

    repositories = await session.execute(
        select(models.Repository).where(
            models.Repository.pulp_href.in_(repo_mapping),
        )
    )
    repositories: List[models.Repository] = repositories.scalars().all()

    if db_record.module:
        release_log.append(f"Module: {db_record.module}\n")

    release_log.extend([
        "Architecture(s): " + ", ".join(arches),
        "\nPackages:\n" + "\n".join(pkgs),
        f"\nForce flag: {force_flag}",
        "\nMissing packages:\n" + "\n".join(missing_pkg_names),
        "\nRepositories:\n" + "\n".join([repo.url for repo in repositories]),
    ])
    return "".join(release_log)


async def get_packages_for_oval(
    packages: List[models.NewErrataPackage],
) -> List[dict]:
    oval_pkgs = []
    albs_pkgs_by_name = collections.defaultdict(list)
    for pkg in packages:
        if pkg.arch == 'src':
            continue
        albs_pkgs = [
            albs_pkg
            for albs_pkg in pkg.albs_packages
            if albs_pkg.status == ErrataPackageStatus.released
        ]
        # This situation should only happen when some packages are missing
        # because the 'force' flag has been enabled
        if not albs_pkgs:
            continue
        for albs_pkg in albs_pkgs:
            albs_pkg_dict = {
                "name": pkg.name,
                "epoch": albs_pkg.epoch,
                "version": albs_pkg.version,
                "release": albs_pkg.release,
                "arch": albs_pkg.arch,
                "reboot_suggested": pkg.reboot_suggested,
            }
            albs_pkgs_by_name[pkg.name].append(albs_pkg_dict)

    # Choose the one with the smallest evr among different versions of the same
    # package but in different arches. This situation happens very often, for
    # example, when not all the architectures of a module have been built
    # in the same build.
    smallest_evrs_by_name = {}
    for name, pkgs in albs_pkgs_by_name.items():
        # yes, this could look a bit wild, but we're comparing similar evrs,
        # yell at me if I'm wrong
        smallest_evrs_by_name[name] = min(
            pkgs,
            key=lambda pkg: f'{pkg["epoch"]}:{pkg["version"]}-{pkg["release"]}',
        )

    noarch_pkgs = [
        pkg for pkg in smallest_evrs_by_name.values() if pkg["arch"] == "noarch"
    ]

    for name, pkgs in albs_pkgs_by_name.items():
        for pkg in pkgs:
            if pkg["arch"] == "noarch":
                continue
            pkg["epoch"] = smallest_evrs_by_name[name]["epoch"]
            pkg["version"] = smallest_evrs_by_name[name]["version"]
            pkg["release"] = smallest_evrs_by_name[name]["release"]
            oval_pkgs.append(pkg)

    # TODO: Consider only adding noarch packages once
    arches = {pkg["arch"] for pkg in oval_pkgs} or [0]
    for pkg in noarch_pkgs:
        for _ in arches:
            oval_pkgs.append(pkg)

    return oval_pkgs


# At this moment we need this cache, but if we finally migrate old records to
# new approach, we can get rid of this redis cache and directly retrieve this
# info from db without passing through get_oval_xml method
async def get_albs_oval_cache(
    session: AsyncSession, platform_name: str
) -> dict:
    redis = aioredis.from_url(settings.redis_url)
    cache_name = f"albs-oval-cache_{platform_name}"
    cached_oval = await redis.get(cache_name)
    if not cached_oval:
        logging.info("Retrieving OVAL cache for %s", platform_name)
        # TODO: uncomment only after production oval data is stored in db
        # as described in https://github.com/AlmaLinux/build-system/issues/350
        # Right now we're using a file for testing
        xml_string = await get_new_oval_xml(session, platform_name, True)
        oval = Composer.load_from_string(xml_string)
        cached_oval = oval.as_dict()
        del cached_oval["definitions"]
        cached_oval = json.dumps(cached_oval)
        await redis.set(cache_name, cached_oval, ex=3600)
    return json.loads(cached_oval)


async def add_oval_data_to_errata_record(
    db_record: models.NewErrataRecord,
    albs_oval_cache: dict,
):
    oval_packages = await get_packages_for_oval(db_record.packages)

    # check if errata includes a devel module
    module = None
    devel_module = None
    if db_record.module:
        module = Module(db_record.module)
        dev_module = f"{module.name}-devel:{module.stream}"
        if dev_module in db_record.original_title:
            devel_module = Module(dev_module)

    oval_ref_ids = {
        "object": [ref["id"] for ref in albs_oval_cache["objects"]],
        "state": [ref["id"] for ref in albs_oval_cache["states"]],
        "test": [ref["id"] for ref in albs_oval_cache["tests"]],
    }

    data_generator = OvalDataGenerator(
        db_record.id,
        Platform(db_record.platform.name),
        oval_packages,
        # TODO: Make the logger optional in liboval
        logging.getLogger(),
        settings.beholder_host,
        oval_ref_ids,
        module=module,
        devel_module=devel_module,
    )

    # Right now, variables are not being generated, so it's a no-op
    # errata.variables = data_generator.generate_variables()
    objects = data_generator.generate_objects(albs_oval_cache["objects"])
    db_record.objects = objects

    states = data_generator.generate_states(albs_oval_cache["states"])
    db_record.states = states

    tests = data_generator.generate_tests(albs_oval_cache["tests"])
    db_record.tests = tests

    db_record.criteria = data_generator.generate_criteria()

    return (objects, states, tests)


async def release_new_errata_record(
    record_id: str, platform_id: int, force: bool
):
    pulp = PulpClient(
        settings.pulp_host,
        settings.pulp_user,
        settings.pulp_password,
    )
    async with open_async_session(key=get_async_db_key()) as session:
        session: AsyncSession
        query = generate_query_for_release([record_id])
        query = query.filter(models.NewErrataRecord.platform_id == platform_id)
        db_record = await session.execute(query)
        db_record: Optional[models.NewErrataRecord] = (
            db_record.scalars().first()
        )
        if not db_record:
            logging.info("Record with %s id doesn't exists", record_id)
            return

        logging.info("Record release %s has been started", record_id)
        search_params = prepare_search_params(db_record)
        logging.info("Retrieving platform packages from pulp")
        pulp_packages = await load_platform_packages(
            db_record.platform,
            search_params,
            for_release=True,
        )
        try:
            repo_mapping, missing_pkg_names = get_albs_packages_from_record(
                db_record,
                pulp_packages,
                force,
            )
        except Exception as exc:
            db_record.release_status = ErrataReleaseStatus.FAILED
            db_record.last_release_log = str(exc)
            logging.exception("Cannot release %s record:", record_id)
            await session.flush()
            return

        logging.info("Creating update record in pulp")
        await process_errata_release_for_repos(
            db_record,
            repo_mapping,
            session,
            pulp,
        )

        logging.info("Generating OVAL data")
        albs_oval_cache = await get_albs_oval_cache(
            session, db_record.platform.name
        )
        await add_oval_data_to_errata_record(db_record, albs_oval_cache)

        db_record.release_status = ErrataReleaseStatus.RELEASED
        db_record.last_release_log = await get_release_logs(
            record_id=record_id,
            pulp_packages=pulp_packages,
            session=session,
            repo_mapping=repo_mapping,
            db_record=db_record,
            force_flag=force,
            missing_pkg_names=missing_pkg_names,
        )
        await session.flush()
        if settings.github_integration_enabled:
            try:
                await close_issues(record_ids=[db_record.id])
            except Exception as err:
                logging.exception(
                    "Cannot move issue to the Released section: %s",
                    err,
                )
    logging.info("Record %s successfully released", record_id)


async def release_errata_record(record_id: str, platform_id: int, force: bool):
    pulp = PulpClient(
        settings.pulp_host,
        settings.pulp_user,
        settings.pulp_password,
    )
    async with open_async_session(key=get_async_db_key()) as session:
        session: AsyncSession
        query = generate_query_for_release([record_id])
        query = query.filter(models.NewErrataRecord.platform_id == platform_id)
        db_record = await session.execute(query)
        db_record: Optional[models.NewErrataRecord] = (
            db_record.scalars().first()
        )
        if not db_record:
            logging.info("Record with %s id doesn't exists", record_id)
            return

        logging.info("Record release %s has been started", record_id)
        search_params = prepare_search_params(db_record)
        logging.info("Retrieving platform packages from pulp")
        pulp_packages = await load_platform_packages(
            db_record.platform,
            search_params,
            for_release=True,
        )
        try:
            repo_mapping, missing_pkg_names = get_albs_packages_from_record(
                db_record,
                pulp_packages,
                force,
            )
        except Exception as exc:
            db_record.release_status = ErrataReleaseStatus.FAILED
            db_record.last_release_log = str(exc)
            logging.exception("Cannot release %s record:", record_id)
            await session.flush()
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
            force_flag=force,
            missing_pkg_names=missing_pkg_names,
        )
        await session.flush()
        if settings.github_integration_enabled:
            try:
                await close_issues(record_ids=[db_record.id])
            except Exception as err:
                logging.exception(
                    "Cannot move issue to the Released section: %s",
                    err,
                )
    logging.info("Record %s successfully released", record_id)


async def bulk_new_errata_records_release(
    records_ids: List[str], force: bool = False
):
    pulp = PulpClient(
        settings.pulp_host,
        settings.pulp_user,
        settings.pulp_password,
    )
    released_record_ids = []
    release_tasks = []
    repos_to_publish = []
    async with open_async_session(key=get_async_db_key()) as session:
        session: AsyncSession
        await session.execute(
            update(models.NewErrataRecord)
            .where(models.NewErrataRecord.id.in_(records_ids))
            .values(
                release_status=ErrataReleaseStatus.IN_PROGRESS,
                last_release_log=None,
            )
        )
        await session.flush()

        db_records = await session.execute(
            generate_query_for_release(records_ids),
        )
        db_records: List[models.NewErrataRecord] = db_records.scalars().all()
        if not db_records:
            logging.info(
                "Cannot find records with the following ids: %s",
                records_ids,
            )
            return

        logging.info(
            "Starting bulk errata release, the following records are"
            " locked: %s",
            [rec.id for rec in db_records],
        )

        platforms = { rec.platform.name for rec in db_records }
        albs_oval_cache = collections.defaultdict()
        for platform in platforms:
            albs_oval_cache[platform] = await get_albs_oval_cache(
                session, platform
            )
        for db_record in db_records:
            search_params = prepare_search_params(db_record)
            logging.info("Retrieving platform packages from pulp")
            pulp_packages = await load_platform_packages(
                db_record.platform,
                search_params,
                for_release=True,
            )
            try:
                repo_mapping, missing_pkg_names = get_albs_packages_from_record(
                    db_record,
                    pulp_packages,
                    force,
                )
            except Exception as exc:
                db_record.release_status = ErrataReleaseStatus.FAILED
                db_record.last_release_log = str(exc)
                logging.exception("Cannot release %s record:", db_record.id)
                continue

            logging.info("Creating update record in pulp")
            tasks = await process_errata_release_for_repos(
                db_record,
                repo_mapping,
                session,
                pulp,
            )

            logging.info("Generating OVAL data")
            objects, states, tests = await add_oval_data_to_errata_record(
                db_record, albs_oval_cache[db_record.platform.name]
            )

            # This way we take into account already generated references
            # during bulk errata release
            for obj in objects:
                if (
                    obj
                    not in albs_oval_cache[db_record.platform.name]["objects"]
                ):
                    albs_oval_cache[db_record.platform.name]["objects"].append(
                        obj
                    )
            for ste in states:
                if (
                    ste
                    not in albs_oval_cache[db_record.platform.name]["states"]
                ):
                    albs_oval_cache[db_record.platform.name]["states"].append(
                        ste
                    )
            for tst in tests:
                if tst not in albs_oval_cache[db_record.platform.name]["tests"]:
                    albs_oval_cache[db_record.platform.name]["tests"].append(
                        tst
                    )

            db_record.release_status = ErrataReleaseStatus.RELEASED
            db_record.last_release_log = await get_release_logs(
                record_id=db_record.id,
                pulp_packages=pulp_packages,
                session=session,
                repo_mapping=repo_mapping,
                db_record=db_record,
                force_flag=force,
                missing_pkg_names=missing_pkg_names,
            )

            released_record_ids.append(db_record.id)

            if not tasks:
                continue
            repos_to_publish.extend(repo_mapping.keys())
            release_tasks.extend(tasks)

    logging.info("Executing release tasks")
    await asyncio.gather(*release_tasks)
    logging.info("Executing publication tasks")
    await asyncio.gather(
        *(pulp.create_rpm_publication(href) for href in set(repos_to_publish))
    )

    if settings.github_integration_enabled:
        try:
            await close_issues(record_ids=[released_record_ids])
        except Exception as err:
            logging.exception(
                "Cannot move issue to the Released section: %s",
                err,
            )

    # TODO: Maybe check whether all ids were released
    logging.info("Successfully released the following erratas: %s", records_ids)


async def bulk_errata_records_release(
    records_ids: List[str], force: bool = False
):
    pulp = PulpClient(
        settings.pulp_host,
        settings.pulp_user,
        settings.pulp_password,
    )
    release_tasks = []
    repos_to_publish = []
    async with open_async_session(key=get_async_db_key()) as session:
        session: AsyncSession
        db_records = await session.execute(
            generate_query_for_release(records_ids),
        )
        db_records: List[models.NewErrataRecord] = db_records.scalars().all()
        if not db_records:
            logging.info(
                "Cannot find records by the following ids: %s",
                records_ids,
            )
            return

        logging.info(
            "Starting bulk errata release, the following records are"
            " locked: %s",
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
                (
                    repo_mapping,
                    missing_pkg_names,
                ) = get_albs_packages_from_record(
                    db_record, pulp_packages, force
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
                missing_pkg_names=missing_pkg_names,
                force_flag=False,
            )
            if settings.github_integration_enabled:
                try:
                    await close_issues(record_ids=[db_record.id])
                except Exception as err:
                    logging.exception(
                        "Cannot move issue to the Released section: %s",
                        err,
                    )
            if not tasks:
                continue
            repos_to_publish.extend(repo_mapping.keys())
            release_tasks.extend(tasks)
    logging.info("Executing release tasks")
    await asyncio.gather(*release_tasks)
    logging.info("Executing publication tasks")
    await asyncio.gather(
        *(pulp.create_rpm_publication(href) for href in set(repos_to_publish))
    )
    logging.info("Bulk errata release is finished")


async def get_updateinfo_xml_from_pulp(
    db: AsyncSession,
    record_id: str,
    platform_id: Optional[int],
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

    platform_name = None
    if platform_id:
        platform_name = (
            await db.execute(
                select(models.Platform.name).where(
                    models.Platform.id == platform_id
                )
            )
        ).scalar()
        if not platform_name:
            return

    cr_upd = cr.UpdateInfo()
    for errata_record in errata_records:
        # Filter out advisories that don't belong to the platform based on
        # advisory's repo name inside pkglist. We rely on the fact that
        # repo names inside advisory's pkglist pulp follow the naming convention
        # {platform_name}-for-{arch}-{stream}-rpms__{major}_{minor}_default,
        # i.e.: almalinux-8-for-x86_64-powertools-rpms__8_9_default
        if platform_name:
            # It'd be very weird to have an advisory without packages
            repo_name = errata_record.get("pkglist", [{}])[0].get("name")
            if not repo_name:
                logging.warning(
                    "Unable to filter results by platform '%s' "
                    "while processing '%s'",
                    platform_name,
                    errata_record["id"],
                )
                return
            if not repo_name.startswith(platform_name.lower()):
                continue

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
    return cr_upd.xml_dump() if cr_upd.updates else None


async def prepare_resetting(
    items_to_insert: List, record: models.NewErrataRecord, session: AsyncSession
):
    search_params = prepare_search_params(record)
    prod_repos_cache = await load_platform_packages(
        platform=record.platform,
        search_params=search_params,
        for_release=False,
        module=record.module,
    )
    await session.execute(
        delete(models.NewErrataToALBSPackage).where(
            models.NewErrataToALBSPackage.errata_package_id.in_(
                (pkg.id for pkg in record.packages)
            )
        )
    )
    for package in record.packages:
        matching_packages, _ = await get_matching_albs_packages(
            session,
            package,
            prod_repos_cache,
            record.module,
        )
        items_to_insert.extend(matching_packages)


async def reset_matched_errata_packages(record_id: str, session: AsyncSession):
    record = (
        (
            await session.execute(
                select(models.NewErrataRecord)
                .where(models.NewErrataRecord.id == record_id)
                .options(
                    selectinload(models.NewErrataRecord.platform).selectinload(
                        models.Platform.repos
                    ),
                    selectinload(models.NewErrataRecord.packages).selectinload(
                        models.NewErrataPackage.albs_packages
                    ),
                )
                .with_for_update()
            )
        )
        .scalars()
        .first()
    )
    if not record:
        return
    items_to_insert = []
    await prepare_resetting(items_to_insert, record, session)
    session.add_all(items_to_insert)
    await session.flush()


async def get_errata_records_threshold(
    issued_date_str: str, session: AsyncSession
):
    issued_date = datetime.datetime.strptime(
        issued_date_str, '%Y-%m-%d %H:%M:%S'
    )
    stmt = (
        select(models.NewErrataRecord)
        .where(models.NewErrataRecord.issued_date >= issued_date)
        .where(
            models.NewErrataRecord.release_status
            == ErrataReleaseStatus.NOT_RELEASED
        )
        .options(
            selectinload(models.NewErrataRecord.platform).selectinload(
                models.Platform.repos
            ),
            selectinload(models.NewErrataRecord.packages).selectinload(
                models.NewErrataPackage.albs_packages
            ),
        )
        .with_for_update()
    )

    records = (await session.execute(stmt)).scalars().all()
    return records


async def reset_matched_erratas_packages_threshold(
    issued_date: str,
):
    async with open_async_session(key=get_async_db_key()) as session:
        records = await get_errata_records_threshold(issued_date, session)
        items_to_insert = []
        for record in records:
            await prepare_resetting(items_to_insert, record, session)
        session.add_all(items_to_insert)
        await session.flush()
    logging.info(
        f'Packages for records {[record.id for record in records]}'
        f' have been matched if their date is later than {issued_date}'
    )


async def set_errata_packages_in_progress(
    records_ids: List[str],
    session: AsyncSession,
):
    db_records = await session.execute(
        select(models.NewErrataRecord).where(
            models.NewErrataRecord.id.in_(records_ids)
        )
    )
    records = db_records.scalars().all()
    records_to_update = [
        record.id
        for record in records
        if record.release_status != ErrataReleaseStatus.IN_PROGRESS
    ]
    skipped_records = [
        record.id
        for record in records
        if record.release_status == ErrataReleaseStatus.IN_PROGRESS
    ]
    if records_to_update:
        await session.execute(
            update(models.NewErrataRecord)
            .where(models.NewErrataRecord.id.in_(records_to_update))
            .values(
                release_status=ErrataReleaseStatus.IN_PROGRESS,
                last_release_log=None,
            )
        )
    return records_to_update, skipped_records

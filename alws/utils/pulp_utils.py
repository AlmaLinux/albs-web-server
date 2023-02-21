import typing
import uuid

from sqlalchemy import select
from sqlalchemy.orm import load_only

from alws.dependencies import get_pulp_db
from alws.pulp_models import (
    CoreContent,
    CoreRepository,
    CoreRepositoryContent,
    RpmModulemd,
    RpmModulemdPackages,
    RpmPackage,
)


def get_uuid_from_pulp_href(pulp_href: str) -> uuid.UUID:
    return uuid.UUID(pulp_href.split("/")[-2])

# TODO: Merge with get_rpm_packages_from_repository
# or keep separate functions but make them share code
def get_rpm_module_packages_from_repository(
    repo_id: uuid.UUID,
    module: str,
    pkg_names: typing.List[str] = None,
    pkg_versions: typing.List[str] = None,
    pkg_epochs: typing.List[str] = None,
) -> typing.List[RpmPackage]:
    module_name, module_stream = module.split(":")
    first_subq = (
        select(CoreRepository.pulp_id)
        .where(CoreRepository.pulp_id == repo_id)
        .scalar_subquery()
    )
    second_subq = (
        select(CoreRepositoryContent.content_id)
        .where(
            CoreRepositoryContent.repository_id == first_subq,
            CoreRepositoryContent.version_removed_id.is_(None),
        )
        .scalar_subquery()
    )
    third_subq = (
        select(CoreContent.pulp_id)
        .where(
            CoreContent.pulp_id.in_(second_subq),
            CoreContent.pulp_type == "rpm.modulemd",
        )
        .scalar_subquery()
    )
    # By default, it should return the modules ordered
    # by version, or that's what I observed so far.
    # If it's not the case, add order_by(RpmModulemd.version)
    # to this subquery.
    # We want to ensure that the first mapping package is
    # taken as the right one later on at get_matching_albs_packages
    fourth_subq = (
        select(RpmModulemd.content_ptr_id)
        .where(
            RpmModulemd.content_ptr_id.in_(third_subq),
            RpmModulemd.name == module_name,
            RpmModulemd.stream == module_stream,
        )
        .scalar_subquery()
    )
    last_subq = (
        select(RpmModulemdPackages.package_id)
        .where(
            RpmModulemdPackages.modulemd_id.in_(fourth_subq),
        )
        .scalar_subquery()
    )

    conditions = [
        RpmPackage.content_ptr_id.in_(last_subq),
    ]
    if pkg_names:
        conditions.append(RpmPackage.name.in_(pkg_names))
    if pkg_versions:
        conditions.append(RpmPackage.version.in_(pkg_versions))
    if pkg_epochs:
        conditions.append(RpmPackage.epoch.in_(pkg_epochs))

    query = select(RpmPackage).where(*conditions)
    with get_pulp_db() as pulp_db:
        return pulp_db.execute(query).scalars().all()


def get_rpm_packages_from_repository(
    repo_id: uuid.UUID,
    pkg_names: typing.List[str] = None,
    pkg_versions: typing.List[str] = None,
    pkg_epochs: typing.List[str] = None,
) -> typing.List[RpmPackage]:
    first_subq = (
        select(CoreRepository.pulp_id)
        .where(CoreRepository.pulp_id == repo_id)
        .scalar_subquery()
    )
    second_subq = (
        select(CoreRepositoryContent.content_id)
        .where(
            CoreRepositoryContent.repository_id == first_subq,
            CoreRepositoryContent.version_removed_id.is_(None),
        )
        .scalar_subquery()
    )
    last_subq = (
        select(CoreContent.pulp_id)
        .where(
            CoreContent.pulp_id.in_(second_subq),
            CoreContent.pulp_type == "rpm.package",
        )
        .scalar_subquery()
    )

    conditions = [
        RpmPackage.content_ptr_id.in_(last_subq),
    ]
    if pkg_names:
        conditions.append(RpmPackage.name.in_(pkg_names))
    if pkg_versions:
        conditions.append(RpmPackage.version.in_(pkg_versions))
    if pkg_epochs:
        conditions.append(RpmPackage.epoch.in_(pkg_epochs))

    query = select(RpmPackage).where(*conditions)
    with get_pulp_db() as pulp_db:
        return pulp_db.execute(query).scalars().all()


def get_rpm_packages_by_ids(
    pulp_pkg_ids: typing.List[uuid.UUID],
    pkg_fields: typing.List[typing.Any],
) -> typing.Dict[str, RpmPackage]:
    result = {}
    with get_pulp_db() as pulp_db:
        pulp_pkgs = (
            pulp_db.execute(
                select(RpmPackage)
                .where(RpmPackage.content_ptr_id.in_(pulp_pkg_ids))
                .options(load_only(*pkg_fields))
            )
            .scalars()
            .all()
        )
        for pkg in pulp_pkgs:
            result[pkg.pulp_href] = pkg
        return result

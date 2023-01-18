import typing
import uuid

from sqlalchemy import select

from alws.dependencies import get_pulp_db
from alws.pulp_models import (
    CoreContent,
    CoreRepository,
    CoreRepositoryContent,
    RpmPackage,
)


def get_uuid_from_pulp_href(pulp_href: str) -> uuid.UUID:
    return uuid.UUID(pulp_href.split("/")[-2])


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

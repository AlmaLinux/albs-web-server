import datetime
from collections import namedtuple
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from alws.errors import PlatformNotFoundError, RepositoriesNotFoundError
from alws.models import Platform, Repository
from alws.pulp_models import CoreRepositoryContent, RpmPackage
from alws.utils.pulp_utils import get_uuid_from_pulp_href


async def get_package_info(
    bs_db: AsyncSession,
    pulp_db: AsyncSession,
    package_name: str,
    platform_name: str,
    arch: Optional[str] = None,
    updated_after: Optional[str] = None,
):
    platform_id_query = select(Platform.id).where(
        Platform.name == platform_name
    )
    platform_id = (await bs_db.execute(platform_id_query)).scalar()

    if not platform_id:
        raise PlatformNotFoundError(f"Invalid distribution: {platform_name}")

    conditions = [
        Repository.platform_id == platform_id,
        Repository.production == True,
    ]
    if arch:
        conditions.append(Repository.arch == arch)

    repo_query = select(Repository).where(*conditions)
    repositories = (await bs_db.execute(repo_query)).scalars().all()

    if not repositories:
        msg = f"No repositories found for {platform_name}.{arch}"
        raise RepositoriesNotFoundError(msg)

    repo_ids = [
        get_uuid_from_pulp_href(repo.pulp_href) for repo in repositories
    ]

    subq_conditions = [
        CoreRepositoryContent.repository_id.in_(repo_ids),
    ]
    if updated_after:
        last_updated = datetime.datetime.strptime(
            updated_after, "%Y-%m-%d %H:%M:%S"
        )
        subq_conditions.append(
            CoreRepositoryContent.pulp_last_updated >= last_updated
        )
    subq = select(CoreRepositoryContent.content_id).where(*subq_conditions)

    query = select(
        RpmPackage.name,
        RpmPackage.version,
        RpmPackage.release,
        RpmPackage.changelogs,
    ).where(
        RpmPackage.name == package_name, RpmPackage.content_ptr_id.in_(subq)
    )

    pulp_packages = (await pulp_db.execute(query)).all()

    PackageTuple = namedtuple(
        "PackageTuple",
        [
            "name",
            "version",
            "release",
            "changelogs",
        ],
    )
    return [PackageTuple(*pulp_pkg)._asdict() for pulp_pkg in pulp_packages]

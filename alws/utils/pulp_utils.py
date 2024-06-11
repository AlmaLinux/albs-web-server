import typing
import uuid

from fastapi_sqla import open_session
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload, load_only

from alws.models import RpmModule
from alws.pulp_models import (
    CoreArtifact,
    CoreContent,
    CoreContentArtifact,
    CoreRepository,
    CoreRepositoryContent,
    RpmModulemd,
    RpmPackage,
)
from alws.utils.modularity import IndexWrapper, get_modules_yaml_from_repo
from alws.utils.parsing import parse_rpm_nevra


def get_uuid_from_pulp_href(pulp_href: str) -> uuid.UUID:
    return uuid.UUID(pulp_href.split("/")[-2])


# TODO: After ALBS-1012 is fixed, we can refactor this function
# to get module packages from pulp without having to grab the actual
# modules.yaml file from the repository
def get_rpm_module_packages_from_repository(
    repo_id: uuid.UUID,
    module: str,
    pkg_names: typing.Optional[typing.List[str]] = None,
    pkg_versions: typing.Optional[typing.List[str]] = None,
    pkg_epochs: typing.Optional[typing.List[str]] = None,
) -> typing.List[RpmPackage]:
    result = []
    repo_query = select(CoreRepository).where(CoreRepository.pulp_id == repo_id)
    with open_session(key="pulp") as pulp_db:
        pulp_db.expire_on_commit = False
        repo = pulp_db.execute(repo_query).scalars().first()
        repo_name = repo.name

    if not repo_name:
        return []

    # TODO: Getting modules.yaml files from BS production repos is not right.
    # The problem here is that we need a way to get packages from
    # the provided module:stream, and pulp actually doesn't have an artifact
    # for it. This is a side effect of our current modules workflow.
    # When building/releasing/publishing modules, we don't actually get
    # them added into pulp, and we should do it.
    # At this moment, we can only trust the modules that are in production
    # repositories.
    try:
        repo_modules_yaml = get_modules_yaml_from_repo(repo_name)
    except Exception:
        return result
    if not repo_modules_yaml:
        return result

    module_name, module_stream = module.split(":")
    devel_module_name = (
        f"{module_name}-devel" if not module_name.endswith("-devel") else ""
    )
    repo_modules = []
    try:
        repo_index = IndexWrapper.from_template(repo_modules_yaml)
    except Exception:
        return result
    for repo_module in repo_index.iter_modules():
        if (
            repo_module.name not in (module_name, devel_module_name)
            or repo_module.stream != module_stream
        ):
            continue
        repo_modules.append(repo_module)
    if not repo_modules:
        return result

    pkg_releases = []
    for repo_module in repo_modules:
        for pkg in repo_module.get_rpm_artifacts():
            pkg_release = parse_rpm_nevra(pkg).release
            if pkg_release not in pkg_releases:
                pkg_releases.append(pkg_release)

    conditions = []

    if pkg_names:
        conditions.append(RpmPackage.name.in_(pkg_names))
    if pkg_versions:
        conditions.append(RpmPackage.version.in_(pkg_versions))
    if pkg_epochs:
        conditions.append(RpmPackage.epoch.in_(pkg_epochs))

    first_subq = (
        select(CoreRepositoryContent.content_id)
        .where(
            CoreRepositoryContent.repository_id == repo.pulp_id,
            CoreRepositoryContent.version_removed_id.is_(None),
        )
        .scalar_subquery()
    )
    last_subq = (
        select(CoreContent.pulp_id)
        .where(
            CoreContent.pulp_id.in_(first_subq),
            CoreContent.pulp_type == "rpm.package",
        )
        .scalar_subquery()
    )

    conditions.extend([
        RpmPackage.content_ptr_id.in_(last_subq),
        RpmPackage.release.in_(pkg_releases),
    ])

    query = select(RpmPackage).where(*conditions)
    with open_session(key="pulp") as pulp_db:
        pulp_db.expire_on_commit = False
        result = pulp_db.execute(query).scalars().all()
    return result


def get_rpm_packages_from_repositories(
    repo_ids: typing.List[uuid.UUID],
    pkg_names: typing.Optional[typing.List[str]] = None,
    pkg_versions: typing.Optional[typing.List[str]] = None,
    pkg_epochs: typing.Optional[typing.List[str]] = None,
    pkg_arches: typing.Optional[typing.List[str]] = None,
    pkg_releases: typing.Optional[typing.List[str]] = None,
) -> typing.List[RpmPackage]:
    conditions = [
        CoreRepository.pulp_id.in_(repo_ids),
        CoreRepositoryContent.version_removed_id.is_(None),
    ]
    if pkg_names:
        conditions.append(RpmPackage.name.in_(pkg_names))
    if pkg_versions:
        conditions.append(RpmPackage.version.in_(pkg_versions))
    if pkg_epochs:
        conditions.append(RpmPackage.epoch.in_(pkg_epochs))
    if pkg_arches:
        conditions.append(RpmPackage.arch.in_(pkg_arches))
    if pkg_releases:
        conditions.append(RpmPackage.release.in_(pkg_releases))
    query = (
        select(RpmPackage)
        .join(CoreContent)
        .join(CoreRepositoryContent)
        .join(CoreRepository)
        .where(*conditions)
        .options(
            joinedload(RpmPackage.content).joinedload(
                CoreContent.core_repositorycontent.and_(
                    CoreRepositoryContent.repository_id.in_(repo_ids)
                )
            )
        )
    )
    with open_session(key="pulp") as pulp_db:
        pulp_db.expire_on_commit = False
        return pulp_db.execute(query).scalars().unique().all()


def get_rpm_packages_from_repository(
    repo_id: uuid.UUID,
    pkg_names: typing.Optional[typing.List[str]] = None,
    pkg_versions: typing.Optional[typing.List[str]] = None,
    pkg_epochs: typing.Optional[typing.List[str]] = None,
    pkg_arches: typing.Optional[typing.List[str]] = None,
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
    if pkg_arches:
        conditions.append(RpmPackage.arch.in_(pkg_arches))

    query = select(RpmPackage).where(*conditions)
    with open_session(key="pulp") as pulp_db:
        pulp_db.expire_on_commit = False
        return pulp_db.execute(query).scalars().all()


def get_rpm_packages_by_ids(
    pulp_pkg_ids: typing.List[uuid.UUID],
    pkg_fields: typing.List[typing.Any],
) -> typing.Dict[str, RpmPackage]:
    result = {}
    with open_session(key="pulp") as pulp_db:
        pulp_db.expire_on_commit = False
        pulp_pkgs = (
            pulp_db.execute(
                select(RpmPackage)
                .where(
                    RpmPackage.content_ptr_id.in_(pulp_pkg_ids),
                )
                .options(
                    joinedload(RpmPackage.content)
                    .joinedload(CoreContent.core_contentartifact)
                    .joinedload(CoreContentArtifact.artifact),
                    load_only(*pkg_fields),
                )
            )
            .unique()
            .scalars()
            .all()
        )
        for pkg in pulp_pkgs:
            result[pkg.pulp_href] = pkg
        return result


def get_rpm_packages_by_checksums(
    pkg_checksums: typing.List[str],
) -> typing.Dict[str, RpmPackage]:
    result = {}
    with open_session(key="pulp") as pulp_db:
        pulp_db.expire_on_commit = False
        pulp_pkgs = (
            pulp_db.execute(
                select(RpmPackage)
                .join(CoreContent)
                .join(CoreContentArtifact)
                .join(CoreArtifact)
                .where(CoreArtifact.sha256.in_(pkg_checksums))
                .options(
                    joinedload(RpmPackage.content)
                    .joinedload(CoreContent.core_contentartifact)
                    .joinedload(CoreContentArtifact.artifact),
                ),
            )
            .unique()
            .scalars()
            .all()
        )
        for package in pulp_pkgs:
            result[package.sha256] = package
        return result


async def get_module_from_pulp_db(
    pulp_db: AsyncSession,
    module: RpmModule,
) -> typing.Optional[RpmModulemd]:
    return (
        (
            await pulp_db.execute(
                select(RpmModulemd).where(
                    RpmModulemd.name == module.name,
                    RpmModulemd.stream == module.stream,
                    RpmModulemd.version == module.version,
                    RpmModulemd.context == module.context,
                    RpmModulemd.arch == module.arch,
                )
            )
        )
        .scalars()
        .first()
    )

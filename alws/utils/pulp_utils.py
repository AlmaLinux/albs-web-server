import typing
import uuid

from sqlalchemy import select
from sqlalchemy.orm import load_only

from alws.dependencies import get_pulp_db
from alws.pulp_models import (
    CoreContent,
    CoreRepository,
    CoreRepositoryContent,
    RpmPackage,
)

from alws.utils.modularity import IndexWrapper, get_modules_yaml_from_repo
from alws.utils.parsing import parse_rpm_nevra


def get_uuid_from_pulp_href(pulp_href: str) -> uuid.UUID:
    return uuid.UUID(pulp_href.split("/")[-2])


# TODO: After ALBS-1012 is fixed, we can refactor this function
# to get module packages from pulp wihtout having to grab the actual
# modules.yaml file from the repository
def get_rpm_module_packages_from_repository(
    repo_id: uuid.UUID,
    module: str,
    pkg_names: typing.List[str] = None,
    pkg_versions: typing.List[str] = None,
    pkg_epochs: typing.List[str] = None,
) -> typing.List[RpmPackage]:
    repo_query = (
        select(CoreRepository)
        .where(CoreRepository.pulp_id == repo_id)
    )
    with get_pulp_db() as pulp_db:
        repo = pulp_db.execute(repo_query).scalars().first()
        repo_name = repo.name

    if not repo_name:
        return

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
    except:
        return

    module_name, module_stream = module.split(':')
    try:
        repo_module = IndexWrapper.from_template(repo_modules_yaml).get_module(
            module_name,
            module_stream
        )
    except:
        return

    pkg_releases = []
    for pkg in repo_module.get_rpm_artifacts():
        pkg_release = parse_rpm_nevra(pkg).release
        if not pkg_release in pkg_releases:
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
    with get_pulp_db() as pulp_db:
        return pulp_db.execute(query).scalars().all()


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

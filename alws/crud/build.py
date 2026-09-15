import logging
import typing

import redis.asyncio as aioredis
import sqlalchemy
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.orm import selectinload
from sqlalchemy.sql.expression import func

from alws import models
from alws.config import settings
from alws.crud.repository import remove_repos_from_pulp
from alws.dramatiq import start_build
from alws.errors import BuildError, DataNotFoundError, PermissionDenied
from alws.perms import actions
from alws.perms.authorization import can_perform
from alws.schemas import build_schema
from alws.utils.pulp_client import PulpClient

BUILDS_PER_PAGE = 10


async def create_build(
    db: AsyncSession,
    build: build_schema.BuildCreate,
    user_id: int,
) -> models.Build:
    logging.error('Build info: %s', build.model_dump())
    product = (
        (
            await db.execute(
                select(models.Product)
                .where(models.Product.id == build.product_id)
                .options(
                    selectinload(models.Product.team)
                    .selectinload(models.Team.roles)
                    .selectinload(models.UserRole.actions),
                    selectinload(models.Product.roles).selectinload(
                        models.UserRole.actions
                    ),
                    selectinload(models.Product.owner),
                )
            )
        )
        .scalars()
        .first()
    )
    if not product:
        raise ValueError(f'Cannot find product with id {build.product_id}')

    user = (
        (
            await db.execute(
                select(models.User)
                .where(models.User.id == user_id)
                .options(
                    selectinload(models.User.roles).selectinload(
                        models.UserRole.actions
                    )
                )
            )
        )
        .scalars()
        .first()
    )
    if not user:
        raise ValueError(f'Cannot find user with id {user_id}')

    if not can_perform(product, user, actions.CreateBuild.name):
        raise PermissionDenied(
            'User has no permissions '
            f'to create build for the product "{product.name}"'
        )

    db_build = models.Build(
        owner_id=user_id,
        mock_options=build.mock_options,
        team_id=product.team_id,
    )
    if build.platform_flavors:
        flavors = await db.execute(
            select(models.PlatformFlavour).where(
                models.PlatformFlavour.id.in_(build.platform_flavors)
            )
        )
        flavors = flavors.scalars().all()
        for flavour in flavors:
            db_build.platform_flavors.append(flavour)
    db.add(db_build)
    await db.flush()
    await db.commit()
    await db.refresh(db_build)
    start_build.send(db_build.id, build.model_dump())
    return db_build


def _build_load_options() -> tuple:
    """
    Eager loaders for everything build_schema.Build serializes.

    Every entry is a separate SELECT ... IN (...) issued by SQLAlchemy, so
    the amount of rows fetched does not depend on how the builds themselves
    were found.
    """
    tasks = selectinload(models.Build.tasks)
    return (
        selectinload(models.Build.owner),
        selectinload(models.Build.linked_builds),
        selectinload(models.Build.platform_flavors),
        selectinload(models.Build.products),
        selectinload(models.Build.sign_tasks),
        tasks.selectinload(models.BuildTask.platform),
        tasks.selectinload(models.BuildTask.ref),
        tasks.selectinload(models.BuildTask.artifacts),
        tasks.selectinload(models.BuildTask.rpm_modules),
        tasks.selectinload(models.BuildTask.performance_stats),
        tasks.selectinload(models.BuildTask.test_tasks).selectinload(
            models.TestTask.performance_stats
        ),
    )


def _build_tasks_exists(
    project: typing.Optional[str] = None,
    ref: typing.Optional[str] = None,
    platform_id: typing.Optional[int] = None,
    build_task_arch: typing.Optional[str] = None,
    pulp_hrefs: typing.Optional[typing.List[str]] = None,
):
    """
    Correlated EXISTS over the build tasks of a build.

    All the task-level conditions live in a single subquery on purpose: they
    have to be satisfied by the same build task, the way an INNER JOIN would
    require it. Compared to joining the tasks into the outer query this
    cannot multiply the build rows, so neither DISTINCT nor a sort of the
    whole result set is needed and Postgres may stop reading builds as soon
    as the page is full.
    """
    subquery = select(1).select_from(models.BuildTask)
    if project is not None or ref is not None:
        subquery = subquery.join(
            models.BuildTaskRef,
            models.BuildTaskRef.id == models.BuildTask.ref_id,
        )
    if pulp_hrefs is not None:
        subquery = subquery.join(
            models.BuildTaskArtifact,
            models.BuildTaskArtifact.build_task_id == models.BuildTask.id,
        )
    subquery = subquery.where(models.BuildTask.build_id == models.Build.id)
    if project is not None:
        subquery = subquery.where(
            models.BuildTaskRef.url.like(f"%/{project}%"),
        )
    if ref is not None:
        subquery = subquery.where(
            sqlalchemy.or_(
                models.BuildTaskRef.url.like(f"%{ref}%"),
                models.BuildTaskRef.git_ref.like(f"%{ref}%"),
            )
        )
    if platform_id is not None:
        subquery = subquery.where(models.BuildTask.platform_id == platform_id)
    if build_task_arch is not None:
        subquery = subquery.where(models.BuildTask.arch == build_task_arch)
    if pulp_hrefs is not None:
        subquery = subquery.where(
            models.BuildTaskArtifact.href.in_(pulp_hrefs),
            models.BuildTaskArtifact.type == "rpm",
        )
    return subquery.correlate(models.Build).exists()


async def _get_pulp_hrefs(
    rpm_name: typing.Optional[str] = None,
    rpm_epoch: typing.Optional[str] = None,
    rpm_version: typing.Optional[str] = None,
    rpm_release: typing.Optional[str] = None,
    rpm_arch: typing.Optional[str] = None,
) -> typing.Optional[typing.List[str]]:
    """
    hrefs of the packages matching the rpm_* filters, None if there are none.

    Resolved once per request: the listing needs the same hrefs for the page
    query and for the count, and asking Pulp twice is a wasted round trip.
    """
    rpm_params = {
        "name": rpm_name,
        "epoch": rpm_epoch,
        "version": rpm_version,
        "release": rpm_release,
        "arch": rpm_arch,
    }
    if not any(rpm_params.values()):
        return None
    pulp_client = PulpClient(
        settings.pulp_host,
        settings.pulp_user,
        settings.pulp_password,
    )
    pulp_params = {
        "fields": ["pulp_href"],
        **{
            key: value
            for key, value in rpm_params.items()
            if value is not None
        },
    }
    # TODO: we can get packages from pulp database
    packages = await pulp_client.get_rpm_packages(**pulp_params)
    return [row["pulp_href"] for row in packages]


async def get_builds(
    db: AsyncSession,
    build_id: typing.Optional[int] = None,
    page_number: typing.Optional[int] = None,
    created_by: typing.Optional[int] = None,
    project: typing.Optional[str] = None,
    ref: typing.Optional[str] = None,
    rpm_name: typing.Optional[str] = None,
    rpm_epoch: typing.Optional[str] = None,
    rpm_version: typing.Optional[str] = None,
    rpm_release: typing.Optional[str] = None,
    rpm_arch: typing.Optional[str] = None,
    platform_id: typing.Optional[int] = None,
    build_task_arch: typing.Optional[str] = None,
    released: typing.Optional[bool] = None,
    signed: typing.Optional[bool] = None,
    is_running: typing.Optional[bool] = None,
) -> typing.Union[models.Build, typing.List[models.Build], dict]:
    if build_id is not None:
        # A lookup by primary key needs no filtering machinery at all.
        result = await db.execute(
            select(models.Build)
            .where(models.Build.id == build_id)
            .where(_build_tasks_exists())
            .options(*_build_load_options())
        )
        return result.scalars().first()

    pulp_hrefs = await _get_pulp_hrefs(
        rpm_name=rpm_name,
        rpm_epoch=rpm_epoch,
        rpm_version=rpm_version,
        rpm_release=rpm_release,
        rpm_arch=rpm_arch,
    )
    conditions = [
        _build_tasks_exists(
            project=project,
            ref=ref,
            platform_id=platform_id,
            build_task_arch=build_task_arch,
            pulp_hrefs=pulp_hrefs,
        )
    ]
    if created_by is not None:
        conditions.append(models.Build.owner_id == created_by)
    if released is not None:
        conditions.append(models.Build.released == released)
    if signed is not None:
        conditions.append(models.Build.signed == signed)
    if is_running is not None:
        conditions.append(
            models.Build.finished_at.is_(None)
            if is_running
            else models.Build.finished_at.is_not(None)
        )

    # `page_number is None` means the caller wants no pagination at all.
    # Anything below the first page is a bad request value rather than a
    # request for every build, so clamp it instead of falling through to
    # the unpaginated branch or building a negative OFFSET below.
    if page_number is not None and page_number < 1:
        page_number = 1

    if page_number is None:
        result = await db.execute(
            select(models.Build)
            .where(*conditions)
            .order_by(models.Build.id.desc())
            .options(*_build_load_options())
        )
        return result.scalars().all()

    # The page is resolved as bare ids first, so that the eager loaders run
    # for the ten builds of the page instead of for every matching build.
    build_ids = (
        (
            await db.execute(
                select(models.Build.id)
                .where(*conditions)
                .order_by(models.Build.id.desc())
                .limit(BUILDS_PER_PAGE)
                .offset(BUILDS_PER_PAGE * (page_number - 1))
            )
        )
        .scalars()
        .all()
    )
    builds = []
    if build_ids:
        builds = (
            (
                await db.execute(
                    select(models.Build)
                    .where(models.Build.id.in_(build_ids))
                    .order_by(models.Build.id.desc())
                    .options(*_build_load_options())
                )
            )
            .scalars()
            .all()
        )
    total_builds = (
        await db.execute(
            select(func.count(models.Build.id)).where(*conditions)
        )
    ).scalar()
    return {
        "builds": builds,
        "total_builds": total_builds,
        "current_page": page_number,
    }


async def get_build_releases(
    db: AsyncSession,
    build_id: int,
) -> typing.List[build_schema.BuildRelease]:
    """
    Every release the build has ever been put into, newest first.

    models.Build.release_id only keeps the release the build got into last,
    so the full history has to be looked up from the releases side. Columns
    are selected explicitly to keep the huge release plan out of the query.
    """
    result = await db.execute(
        select(
            models.Release.id,
            models.Release.status,
            models.Release.created_at,
            models.Platform.name.label("platform_name"),
            models.Product.name.label("product_name"),
        )
        .join(
            models.Platform,
            models.Release.platform_id == models.Platform.id,
        )
        .join(
            models.Product,
            models.Release.product_id == models.Product.id,
        )
        .where(models.Release.build_ids.any(build_id))
        .order_by(models.Release.id.desc())
    )
    return [build_schema.BuildRelease(**row._asdict()) for row in result.all()]


async def get_module_preview(
    redis: aioredis.client.Redis,
    platform: models.Platform,
    flavors: typing.List[models.PlatformFlavour],
    module_request: build_schema.ModulePreviewRequest,
) -> build_schema.ModulePreview:
    refs, modules, enabled_modules = await build_schema.get_module_refs(
        redis=redis,
        task=module_request.ref,
        platform=platform,
        flavors=flavors,
        platform_arches=module_request.platform_arches,
    )
    return build_schema.ModulePreview(
        refs=refs,
        module_name=module_request.ref.git_repo_name,
        module_stream=module_request.ref.module_stream_from_ref(),
        modules_yaml='\n'.join(modules),
        enabled_modules=enabled_modules,
        git_ref=module_request.ref.git_ref,
    )


def get_task_data_from_build(build: models.Build):
    repos = []
    repo_ids = []
    build_task_ids = []
    build_task_artifact_ids = []
    build_task_ref_ids = []
    test_task_ids = []
    test_task_artifact_ids = []
    for bt in build.tasks:
        build_task_ids.append(bt.id)
        build_task_ref_ids.append(bt.ref_id)
        for build_artifact in bt.artifacts:
            build_task_artifact_ids.append(build_artifact.id)
        for tt in bt.test_tasks:
            test_task_ids.append(tt.id)
            repo_ids.append(tt.repository_id)
            for test_artifact in tt.artifacts:
                test_task_artifact_ids.append(test_artifact.id)
    for br in build.repos:
        repos.append(br.pulp_href)
        repo_ids.append(br.id)
    return (
        repos,
        repo_ids,
        build_task_ids,
        build_task_artifact_ids,
        build_task_ref_ids,
        test_task_ids,
        test_task_artifact_ids,
    )


async def remove_build_data(db: AsyncSession, build: models.Build):
    (
        repos,
        repo_ids,
        build_task_ids,
        build_task_artifact_ids,
        build_task_ref_ids,
        test_task_ids,
        test_task_artifact_ids,
    ) = get_task_data_from_build(build)
    build_id = build.id
    await db.execute(
        delete(models.BuildRepo).where(models.BuildRepo.c.build_id == build_id)
    )
    await db.execute(
        delete(models.BuildPlatformFlavour).where(
            models.BuildPlatformFlavour.c.build_id == build_id
        )
    )
    await db.execute(
        delete(models.SignTask).where(models.SignTask.build_id == build_id)
    )
    await db.execute(
        delete(models.BinaryRpm).where(models.BinaryRpm.build_id == build_id)
    )
    await db.execute(
        delete(models.SourceRpm).where(models.SourceRpm.build_id == build_id)
    )
    await db.execute(
        delete(models.PerformanceStats).where(
            models.PerformanceStats.build_task_id.in_(build_task_ids)
        )
    )
    await db.execute(
        delete(models.PerformanceStats).where(
            models.PerformanceStats.test_task_id.in_(test_task_ids)
        )
    )
    await db.execute(
        delete(models.TestTaskArtifact).where(
            models.TestTaskArtifact.id.in_(test_task_artifact_ids)
        )
    )
    await db.execute(
        delete(models.TestTask).where(models.TestTask.id.in_(test_task_ids))
    )
    await db.execute(
        delete(models.BuildTaskArtifact).where(
            models.BuildTaskArtifact.id.in_(build_task_artifact_ids)
        )
    )
    await db.execute(
        delete(models.BuildTaskDependency).where(
            models.BuildTaskDependency.c.build_task_dependency.in_(
                build_task_ids
            )
        )
    )
    await db.execute(
        delete(models.Repository).where(models.Repository.id.in_(repo_ids))
    )
    await db.execute(
        delete(models.BuildTask).where(models.BuildTask.build_id == build_id)
    )
    await db.execute(
        delete(models.BuildDependency).where(
            sqlalchemy.or_(
                models.BuildDependency.c.build_dependency == build_id,
                models.BuildDependency.c.build_id == build_id,
            )
        )
    )
    await db.execute(
        delete(models.BuildTaskRef).where(
            models.BuildTaskRef.id.in_(build_task_ref_ids)
        )
    )
    await db.execute(delete(models.Build).where(models.Build.id == build_id))
    # FIXME
    # it seems we cannot just delete any files because
    # https://docs.pulpproject.org/pulpcore/restapi.html#tag/Content:-Files
    # does not content delete option, but artifact does:
    # https://docs.pulpproject.org/pulpcore/restapi.html#operation/
    # artifacts_delete
    # "Remove Artifact only if it is not associated with any Content."
    # for artifact in artifacts:
    # await pulp_client.remove_artifact(artifact)
    try:
        await remove_repos_from_pulp(repos)
    except Exception as err:
        logging.exception("Cannot delete repo from pulp: %s", err)


async def remove_build_job(db: AsyncSession, build_id: int):
    query_bj = (
        select(models.Build)
        .where(models.Build.id == build_id)
        .options(
            selectinload(models.Build.tasks).selectinload(
                models.BuildTask.artifacts
            ),
            selectinload(models.Build.repos),
            selectinload(models.Build.products),
            selectinload(models.Build.tasks)
            .selectinload(models.BuildTask.test_tasks)
            .selectinload(models.TestTask.artifacts),
        )
    )
    build = await db.execute(query_bj)
    build = build.scalars().first()
    if build is None:
        raise DataNotFoundError(f'Build with {build_id} not found')
    if build.products:
        product_names = "\n".join((product.name for product in build.products))
        raise BuildError(
            f"Cannot delete Build={build_id}, "
            f"build contains in following products:\n{product_names}"
        )
    if build.released:
        raise BuildError(f"Build with {build_id} is released")
    await remove_build_data(db, build)

import logging
import typing

import sqlalchemy
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.orm import selectinload
from sqlalchemy.sql.expression import func

from alws import models
from alws.config import settings
from alws.dramatiq import start_build
from alws.errors import BuildError, DataNotFoundError, PermissionDenied
from alws.perms import actions
from alws.perms.authorization import can_perform
from alws.schemas import build_schema
from alws.utils.github_integration_helper import (
    find_issues_by_repo_name,
    get_github_client,
    move_issues,
    set_build_id_to_issues,
)
from alws.utils.parsing import parse_rpm_nevra
from alws.utils.pulp_client import PulpClient


async def create_build(
    db: AsyncSession,
    build: build_schema.BuildCreate,
    user_id: int,
) -> models.Build:
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
    await db.commit()
    await db.refresh(db_build)
    start_build.send(db_build.id, build.model_dump())
    if settings.github_integration_enabled:
        try:
            github_client = await get_github_client()
            repos = set()
            for task in build.tasks:
                if isinstance(task, build_schema.BuildTaskModuleRef):
                    repos.add(f"module {task.module_name}")
                    continue

                repos.add(f"{task.url} {task.git_ref}")
            issues = await find_issues_by_repo_name(
                github_client=github_client,
                repo_names=list(repos),
            )
            if issues:
                await set_build_id_to_issues(
                    github_client=github_client,
                    issues=issues,
                    build_id=db_build.id,
                )
                await move_issues(
                    github_client=github_client,
                    issues=issues,
                    status="Building",
                )
        except Exception as err:
            logging.exception(
                "Cannot move issue to the Building section: %s",
                err,
            )
    return db_build


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
    pulp_params = {
        "fields": ["pulp_href"],
    }
    pulp_client = PulpClient(
        settings.pulp_host,
        settings.pulp_user,
        settings.pulp_password,
    )
    rpm_params = {
        "name": rpm_name,
        "epoch": rpm_epoch,
        "version": rpm_version,
        "release": rpm_release,
        "arch": rpm_arch,
    }

    async def generate_query(count=False):
        query = (
            select(models.Build)
            .join(
                models.Build.tasks,
            )
            .join(
                models.BuildTask.ref,
            )
            .join(
                models.BuildTask.artifacts,
                isouter=True,
            )
            .order_by(models.Build.id.desc())
            .options(
                selectinload(models.Build.tasks).selectinload(
                    models.BuildTask.platform
                ),
                selectinload(models.Build.tasks).selectinload(
                    models.BuildTask.ref
                ),
                selectinload(models.Build.owner),
                selectinload(models.Build.tasks).selectinload(
                    models.BuildTask.artifacts
                ),
                selectinload(models.Build.linked_builds),
                selectinload(models.Build.tasks)
                .selectinload(models.BuildTask.test_tasks)
                .selectinload(models.TestTask.performance_stats),
                selectinload(models.Build.tasks).selectinload(
                    models.BuildTask.performance_stats
                ),
                selectinload(models.Build.sign_tasks),
                selectinload(models.Build.tasks).selectinload(
                    models.BuildTask.rpm_module
                ),
                selectinload(models.Build.platform_flavors),
                selectinload(models.Build.products),
            )
            .distinct(models.Build.id)
        )

        if build_id is not None:
            query = query.where(models.Build.id == build_id)
        if project is not None:
            project_name = project
            project_query = query.filter(
                sqlalchemy.or_(
                    models.BuildTaskRef.url.like(f"%/{project_name}.git"),
                    models.BuildTaskRef.url.like(f"%/{project_name}%.src.rpm"),
                    models.BuildTaskRef.url.like(
                        f"%/rpms/{project_name}%.git"
                    ),
                )
            )
            if not (await db.execute(project_query)).scalars().all():
                project_query = query.filter(
                    models.BuildTaskRef.url.like(f"%/{project_name}%"),
                )
            query = project_query
        if created_by is not None:
            query = query.filter(
                models.Build.owner_id == created_by,
            )
        if ref is not None:
            query = query.filter(
                sqlalchemy.or_(
                    models.BuildTaskRef.url.like(f"%{ref}%"),
                    models.BuildTaskRef.git_ref.like(f"%{ref}%"),
                )
            )
        if platform_id is not None:
            query = query.filter(models.BuildTask.platform_id == platform_id)
        if build_task_arch is not None:
            query = query.filter(models.BuildTask.arch == build_task_arch)
        if any(rpm_params.values()):
            pulp_params.update({
                key: value
                for key, value in rpm_params.items()
                if value is not None
            })
            # TODO: we can get packages from pulp database
            pulp_hrefs = await pulp_client.get_rpm_packages(**pulp_params)
            pulp_hrefs = [row["pulp_href"] for row in pulp_hrefs]
            query = query.filter(
                sqlalchemy.and_(
                    models.BuildTaskArtifact.href.in_(pulp_hrefs),
                    models.BuildTaskArtifact.type == "rpm",
                )
            )
        if released is not None:
            query = query.filter(models.Build.released == released)
        if signed is not None:
            query = query.filter(models.Build.signed == signed)
        if is_running is not None:
            query = query.filter(
                models.Build.finished_at.is_(None)
                if is_running
                else models.Build.finished_at.is_not(None)
            )
        if page_number and not count:
            query = query.slice(10 * page_number - 10, 10 * page_number)
        if count:
            query = select(func.count()).select_from(query)
        return query

    if build_id:
        query = await db.execute(await generate_query())
        return query.scalars().first()
    if page_number:
        return {
            "builds": (
                (await db.execute(await generate_query())).scalars().all()
            ),
            "total_builds": (
                await db.execute(await generate_query(count=True))
            ).scalar(),
            "current_page": page_number,
        }
    query = await db.execute(await generate_query())
    return query.scalars().all()


async def get_module_preview(
    platform: models.Platform,
    flavors: typing.List[models.PlatformFlavour],
    module_request: build_schema.ModulePreviewRequest,
) -> build_schema.ModulePreview:
    refs, modules, enabled_modules = await build_schema.get_module_refs(
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
    repos = []
    repo_ids = []
    build_task_ids = []
    build_task_artifact_ids = []
    build_task_ref_ids = []
    test_task_ids = []
    test_task_artifact_ids = []
    async with db.begin():
        build = await db.execute(query_bj)
        build = build.scalars().first()
        if build is None:
            raise DataNotFoundError(f'Build with {build_id} not found')
        if build.products:
            product_names = "\n".join(
                (product.name for product in build.products)
            )
            raise BuildError(
                f"Cannot delete Build={build_id}, "
                f"build contains in following products:\n{product_names}"
            )
        if build.released:
            raise BuildError(f"Build with {build_id} is released")
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
        pulp_client = PulpClient(
            settings.pulp_host, settings.pulp_user, settings.pulp_password
        )
        await db.execute(
            delete(models.BuildRepo).where(
                models.BuildRepo.c.build_id == build_id
            )
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
            delete(models.BinaryRpm).where(
                models.BinaryRpm.build_id == build_id
            )
        )
        await db.execute(
            delete(models.SourceRpm).where(
                models.SourceRpm.build_id == build_id
            )
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
            delete(models.TestTask).where(
                models.TestTask.id.in_(test_task_ids)
            )
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
            delete(models.BuildTask).where(
                models.BuildTask.build_id == build_id
            )
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
        await db.execute(
            delete(models.Build).where(models.Build.id == build_id)
        )
        # FIXME
        # it seems we cannot just delete any files because
        # https://docs.pulpproject.org/pulpcore/restapi.html#tag/Content:-Files
        # does not content delete option, but artifact does:
        # https://docs.pulpproject.org/pulpcore/restapi.html#operation/
        # artifacts_delete
        # "Remove Artifact only if it is not associated with any Content."
        # for artifact in artifacts:
        # await pulp_client.remove_artifact(artifact)
        for repo in repos:
            try:
                await pulp_client.delete_by_href(repo, wait_for_result=True)
            except Exception as err:
                logging.exception("Cannot delete repo from pulp: %s", err)
        await db.commit()

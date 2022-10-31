import logging
import typing

import sqlalchemy
from sqlalchemy import delete
from sqlalchemy.future import select
from sqlalchemy.orm import Session, selectinload
from sqlalchemy.sql.expression import func

from alws import models
from alws.config import settings
from alws.errors import (
    BuildError,
    DataNotFoundError,
    PermissionDenied,
)
from alws.perms import actions
from alws.perms.authorization import can_perform
from alws.schemas import build_schema
from alws.utils.pulp_client import PulpClient
from alws.dramatiq import start_build


async def create_build(
            db: Session,
            build: build_schema.BuildCreate,
            user_id: int,
        ) -> models.Build:

    product = (await db.execute(select(models.Product).where(
        models.Product.id == build.product_id).options(
        selectinload(models.Product.team).selectinload(
            models.Team.roles).selectinload(models.UserRole.actions),
        selectinload(
            models.Product.roles).selectinload(models.UserRole.actions),
        selectinload(models.Product.owner),
    ))).scalars().first()
    if not product:
        raise ValueError(f'Cannot find product with id {build.product_id}')

    user = (await db.execute(select(models.User).where(
        models.User.id == user_id).options(
        selectinload(models.User.roles).selectinload(models.UserRole.actions)
    ))).scalars().first()
    if not user:
        raise ValueError(f'Cannot find user with id {user_id}')

    if not can_perform(product, user, actions.CreateBuild.name):
        raise PermissionDenied(
            f'User has no permissions '
            f'to create build for the product "{product.name}"'
        )

    db_build = models.Build(
        owner_id=user_id,
        mock_options=build.mock_options,
        team_id=product.team_id,
    )
    if build.platform_flavors:
        flavors = await db.execute(select(models.PlatformFlavour).where(
            models.PlatformFlavour.id.in_(build.platform_flavors)
        ))
        flavors = flavors.scalars().all()
        for flavour in flavors:
            db_build.platform_flavors.append(flavour)
    db.add(db_build)
    await db.commit()
    await db.refresh(db_build)
    start_build.send(db_build.id, build.dict())
    return db_build


async def get_builds(
            db: Session,
            build_id: typing.Optional[int] = None,
            page_number: typing.Optional[int] = None,
            search_params: build_schema.BuildSearch = None,
        ) -> typing.Union[models.Build, typing.List[models.Build], dict]:
    query = select(models.Build).join(
        models.Build.tasks,
    ).join(
        models.BuildTask.ref,
    ).join(
        models.BuildTask.artifacts,
        isouter=True,
    ).order_by(models.Build.id.desc()).options(
        selectinload(models.Build.tasks).selectinload(
            models.BuildTask.platform),
        selectinload(models.Build.tasks).selectinload(models.BuildTask.ref),
        selectinload(models.Build.owner),
        selectinload(models.Build.tasks).selectinload(
            models.BuildTask.artifacts),
        selectinload(models.Build.linked_builds),
        selectinload(models.Build.tasks).selectinload(
            models.BuildTask.test_tasks),
        selectinload(models.Build.sign_tasks),
        selectinload(models.Build.tasks).selectinload(
            models.BuildTask.rpm_module),
        selectinload(models.Build.platform_flavors),
        selectinload(models.Build.products)
    ).distinct(models.Build.id)

    pulp_params = {
        'fields': ['pulp_href'],
    }
    pulp_client = PulpClient(
        settings.pulp_host,
        settings.pulp_user,
        settings.pulp_password,
    )

    if page_number:
        query = query.slice(10 * page_number - 10, 10 * page_number)
    if build_id is not None:
        query = query.where(models.Build.id == build_id)
    if search_params is not None:
        if search_params.project is not None:
            project_name = search_params.project
            project_query = query.filter(sqlalchemy.or_(
                models.BuildTaskRef.url.like(f'%/{project_name}.git'),
                models.BuildTaskRef.url.like(f'%/{project_name}%.src.rpm'),
                models.BuildTaskRef.url.like(f'%/rpms/{project_name}%.git'),
            ))
            if not (await db.execute(project_query)).scalars().all():
                project_query = query.filter(
                    models.BuildTaskRef.url.like(f'%/{project_name}%'),
                )
            query = project_query
        if search_params.created_by is not None:
            query = query.filter(
                models.Build.owner_id == search_params.created_by)
        if search_params.ref is not None:
            query = query.filter(sqlalchemy.or_(
                models.BuildTaskRef.url.like(f'%{search_params.ref}%'),
                models.BuildTaskRef.git_ref.like(f'%{search_params.ref}%'),
            ))
        if search_params.platform_id is not None:
            query = query.filter(
                models.BuildTask.platform_id == search_params.platform_id)
        if search_params.build_task_arch is not None:
            query = query.filter(
                models.BuildTask.arch == search_params.build_task_arch)
        if search_params.is_package_filter:
            pulp_params.update({
                key.replace('rpm_', ''): value
                for key, value in search_params.dict().items()
                if key.startswith('rpm_') and value is not None
            })
            pulp_hrefs = await pulp_client.get_rpm_packages(**pulp_params)
            pulp_hrefs = [row['pulp_href'] for row in pulp_hrefs]
            query = query.filter(sqlalchemy.and_(
                models.BuildTaskArtifact.href.in_(pulp_hrefs),
                models.BuildTaskArtifact.type == 'rpm',
            ))
        if search_params.released is not None:
            query = query.filter(
                models.Build.released == search_params.released)
        if search_params.signed is not None:
            query = query.filter(models.Build.signed == search_params.signed)
    result = await db.execute(query)
    if build_id:
        return result.scalars().first()
    elif page_number:
        total_builds = await db.execute(func.count(models.Build.id))
        total_builds = total_builds.scalar()
        return {'builds': result.scalars().all(),
                'total_builds': total_builds,
                'current_page': page_number}
    return result.scalars().all()


async def get_module_preview(
                platform: models.Platform,
                flavors: typing.List[models.PlatformFlavour],
                module_request: build_schema.ModulePreviewRequest
            ) -> build_schema.ModulePreview:
    refs, modules = await build_schema.get_module_refs(
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
        git_ref=module_request.ref.git_ref,
    )


async def remove_build_job(db: Session, build_id: int):
    query_bj = select(models.Build).where(
        models.Build.id == build_id).options(
        selectinload(models.Build.tasks).selectinload(
            models.BuildTask.artifacts),
        selectinload(models.Build.repos),
        selectinload(models.Build.products),
        selectinload(models.Build.tasks).selectinload(
            models.BuildTask.test_tasks).selectinload(
            models.TestTask.artifacts)
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
            product_names = "\n".join((
                product.name
                for product in build.products
            ))
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
            settings.pulp_host,
            settings.pulp_user,
            settings.pulp_password
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
        await db.execute(
            delete(models.BuildRepo).where(models.BuildRepo.c.build_id == build_id)
        )
        await db.execute(delete(models.BuildPlatformFlavour).where(
            models.BuildPlatformFlavour.c.build_id == build_id))
        await db.execute(
            delete(models.SignTask).where(
                models.SignTask.build_id == build_id)
        )
        await db.execute(delete(models.BinaryRpm).where(
            models.BinaryRpm.build_id == build_id))
        await db.execute(delete(models.SourceRpm).where(
            models.SourceRpm.build_id == build_id))
        await db.execute(
            delete(models.BuildTaskArtifact).where(
                models.BuildTaskArtifact.id.in_(build_task_artifact_ids))
        )
        await db.execute(
            delete(models.TestTaskArtifact).where(
                models.TestTaskArtifact.id.in_(test_task_artifact_ids))
        )
        await db.execute(
            delete(models.TestTask).where(
                models.TestTask.id.in_(test_task_ids))
        )
        await db.execute(
            delete(models.BuildTaskDependency).where(
                models.BuildTaskDependency.c.build_task_dependency.in_(build_task_ids))
        )
        await db.execute(
            delete(models.BuildTask).where(
                models.BuildTask.id.in_(build_task_ids))
        )
        await db.execute(
            delete(models.Repository).where(
                models.Repository.id.in_(repo_ids))
        )
        await db.execute(
            delete(models.BuildTask).where(models.BuildTask.build_id == build_id)
        )
        await db.execute(
            delete(models.BuildDependency).where(sqlalchemy.or_(
                models.BuildDependency.c.build_dependency == build_id,
                models.BuildDependency.c.build_id == build_id,
            ))
        )
        await db.execute(
            delete(models.BuildTaskRef).where(
                models.BuildTaskRef.id.in_(build_task_ref_ids))
        )
        await db.execute(
            delete(models.Build).where(models.Build.id == build_id))
        await db.commit()

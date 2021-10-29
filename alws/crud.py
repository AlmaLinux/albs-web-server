import typing
import datetime
import collections

import sqlalchemy
from sqlalchemy import update, delete
from sqlalchemy.future import select
from sqlalchemy.orm import Session, selectinload
from sqlalchemy.sql.expression import func

from alws import models
from alws.errors import DataNotFoundError, BuildError, DistributionError
from alws.config import settings
from alws.releases import (
    execute_release_plan,
    get_release_plan,
    EmptyReleasePlan,
    MissingRepository,
)
from alws.utils.pulp_client import PulpClient
from alws.utils.github import get_user_github_token, get_github_user_info
from alws.utils.jwt_utils import generate_JWT_token
from alws.constants import BuildTaskStatus, TestTaskStatus, ReleaseStatus
from alws.build_planner import BuildPlanner
from alws.schemas import (
    build_schema, user_schema, platform_schema, build_node_schema,
    distro_schema, test_schema, release_schema, remote_schema,
    repository_schema,
)
from alws.utils.distro_utils import create_empty_repo


__all__ = [
    'add_distributions_after_rebuild',
    'create_build',
    'create_platform',
    'get_builds',
    'get_platforms',
    'update_failed_build_items',
]


async def create_build(
            db: Session,
            build: build_schema.BuildCreate,
            user_id: int
        ) -> models.Build:
    async with db.begin():
        planner = BuildPlanner(db, user_id, build.platforms)
        await planner.load_platforms()
        for task in build.tasks:
            await planner.add_task(task)
        if build.linked_builds:
            for linked_id in build.linked_builds:
                linked_build = await get_builds(db, linked_id)
                if linked_build:
                    await planner.add_linked_builds(linked_build)
        if build.mock_options:
            planner.add_mock_options(build.mock_options)
        db_build = planner.create_build()
        db.add(db_build)
        await db.flush()
        await db.refresh(db_build)
        await planner.init_build_repos()
        await db.commit()
    # TODO: this is ugly hack for now
    return await get_builds(db, db_build.id)


async def get_builds(
            db: Session,
            build_id: typing.Optional[int] = None,
            page_number: typing.Optional[int] = None
        ) -> typing.Union[typing.List[models.Build], dict]:
    query = select(models.Build).order_by(models.Build.id.desc()).options(
        selectinload(models.Build.tasks).selectinload(
            models.BuildTask.platform),
        selectinload(models.Build.tasks).selectinload(models.BuildTask.ref),
        selectinload(models.Build.user),
        selectinload(models.Build.tasks).selectinload(
            models.BuildTask.artifacts),
        selectinload(models.Build.linked_builds)
    )
    if page_number:
        query = query.slice(10 * page_number - 10, 10 * page_number)
    if build_id is not None:
        query = query.where(models.Build.id == build_id)
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


async def modify_platform(
            db: Session,
            platform: platform_schema.PlatformModify
        ) -> models.Platform:
    query = models.Platform.name == platform.name
    async with db.begin():
        db_platform = await db.execute(
            select(models.Platform).where(query).options(
                selectinload(models.Platform.repos)
            ).with_for_update()
        )
        db_platform = db_platform.scalars().first()
        if not db_platform:
            raise DataNotFoundError(
                f'Platform with name: "{platform.name}" does not exists'
            )
        for key in ('type', 'distr_type', 'distr_version', 'arch_list',
                    'data'):
            value = getattr(platform, key, None)
            if value is not None:
                setattr(db_platform, key, value)
        db_repos = {repo.name: repo for repo in db_platform.repos}
        new_repos = {repo.name: repo for repo in platform.repos}
        for repo in platform.repos:
            if repo.name in db_repos:
                db_repo = db_repos[repo.name]
                for key in repo.dict().keys():
                    setattr(db_repo, key, getattr(repo, key))
            else:
                db_platform.repos.append(models.Repository(**repo.dict()))
        to_remove = []
        for repo_name in db_repos:
            if repo_name not in new_repos:
                to_remove.append(repo_name)
        remove_query = models.Repository.name.in_(to_remove)
        await db.execute(
            delete(models.BuildTaskDependency).where(remove_query)
        )
        await db.commit()
    await db.refresh(db_platform)
    return db_platform


async def create_platform(
            db: Session,
            platform: platform_schema.PlatformCreate
        ) -> models.Platform:
    db_platform = models.Platform(
        name=platform.name,
        type=platform.type,
        distr_type=platform.distr_type,
        distr_version=platform.distr_version,
        test_dist_name=platform.test_dist_name,
        data=platform.data,
        arch_list=platform.arch_list
    )
    for repo in platform.repos:
        db_platform.repos.append(models.Repository(**repo.dict()))
    db.add(db_platform)
    await db.commit()
    await db.refresh(db_platform)
    return db_platform


async def create_distro(
        db: Session,
        distribution: distro_schema.DistroCreate
) -> models.Distribution:

    async with db.begin():
        db_distro = await db.execute(select(models.Distribution).where(
            models.Distribution.name.__eq__(distribution.name)))
        db_distro = db_distro.scalars().first()

        if db_distro:
            error_msg = f'{distribution.name} distribution already exists'
            raise DistributionError(error_msg)

        distro_platforms = await db.execute(select(models.Platform).where(
            models.Platform.name.in_(distribution.platforms)))
        distro_platforms = distro_platforms.scalars().all()

        db_distribution = models.Distribution(
            name=distribution.name
        )
        db_distribution.platforms.extend(distro_platforms)

        pulp_client = PulpClient(
            settings.pulp_host,
            settings.pulp_user,
            settings.pulp_password
        )
        await create_empty_repo(pulp_client, db_distribution)
        db.add(db_distribution)
        await db.commit()
    await db.refresh(db_distribution)
    return db_distribution


async def get_platforms(db):
    db_platforms = await db.execute(select(models.Platform))
    return db_platforms.scalars().all()


async def get_distributions(db):
    db_distros = await db.execute(select(models.Distribution))
    return db_distros.scalars().all()


async def add_distributions_after_rebuild(
        db: Session,
        request: build_node_schema.BuildDone,
):

    subquery = select(models.BuildTask.build_id).where(
        models.BuildTask.id == request.task_id).scalar_subquery()
    build_query = select(models.Build).where(
        models.Build.id == subquery,
    ).options(
        selectinload(
            models.Build.tasks).selectinload(models.BuildTask.artifacts),
    )
    db_build = await db.execute(build_query)
    db_build = db_build.scalars().first()

    build_completed = all((
        task.status >= BuildTaskStatus.COMPLETED
        for task in db_build.tasks
    ))
    if not build_completed:
        return

    distr_query = select(models.Distribution).join(
        models.Distribution.builds,
    ).where(models.Build.id == db_build.id).options(
        selectinload(models.Distribution.builds),
        selectinload(models.Distribution.repositories),
    )
    db_distros = await db.execute(distr_query)
    db_distros = db_distros.scalars().all()

    pulp_client = PulpClient(settings.pulp_host, settings.pulp_user,
                             settings.pulp_password)

    for db_distro in db_distros:
        modify = await prepare_repo_modify_dict(db_build, db_distro)
        for modification in ('remove', 'add'):
            for key, value in modify.items():
                if modification == 'add':
                    await pulp_client.modify_repository(
                        add=value, repo_to=key)
                else:
                    await pulp_client.modify_repository(
                        remove=value, repo_to=key)


async def prepare_repo_modify_dict(db_build: models.Build,
                                   db_distro: models.Distribution):
    modify = collections.defaultdict(list)
    for task in db_build.tasks:
        for artifact in task.artifacts:
            if artifact.type != 'rpm':
                continue
            build_artifact = build_node_schema.BuildDoneArtifact.from_orm(
                artifact)
            for distro_repo in db_distro.repositories:
                if (distro_repo.arch == task.arch and
                        distro_repo.debug == build_artifact.is_debuginfo):
                    modify[distro_repo.pulp_href].append(artifact.href)
    return modify


async def modify_distribution(build_id: int, distribution: str, db: Session,
                              modification: str):

    async with db.begin():
        db_distro = await db.execute(select(models.Distribution).where(
            models.Distribution.name.__eq__(distribution)
        ).options(selectinload(models.Distribution.repositories),
                  selectinload(models.Distribution.builds))
        )
        db_distro = db_distro.scalars().first()

        db_build = await db.execute(select(models.Build).where(
            models.Build.id.__eq__(build_id)
        ).options(selectinload(models.Build.tasks).selectinload(
                  models.BuildTask.artifacts))
        )
        db_build = db_build.scalars().first()

        pulp_client = PulpClient(settings.pulp_host, settings.pulp_user,
                                 settings.pulp_password)

        if modification == 'add':
            if db_build in db_distro.builds:
                error_msg = f'Packages of build {build_id} have already been' \
                            f' added to {distribution} distribution'
                raise DistributionError(error_msg)
            db_distro.builds.append(db_build)
        if modification == 'remove':
            if db_build not in db_distro.builds:
                error_msg = f'Packages of build {build_id} cannot be removed ' \
                            f'from {distribution} distribution ' \
                            f'as they are not added there'
                raise DistributionError(error_msg)
            remove_query = models.Build.id.__eq__(build_id)
            await db.execute(
                delete(models.DistributionBuilds).where(remove_query)
            )

        await db.commit()
    await db.refresh(db_distro)
    modify = await prepare_repo_modify_dict(db_build, db_distro)
    for key, value in modify.items():
        if modification == 'add':
            await pulp_client.modify_repository(add=value, repo_to=key)
        else:
            await pulp_client.modify_repository(remove=value, repo_to=key)


async def get_available_build_task(
            db: Session,
            request: build_node_schema.RequestTask
        ) -> models.BuildTask:
    async with db.begin():
        # TODO: here should be config value
        ts_expired = datetime.datetime.now() - datetime.timedelta(minutes=20)
        query = ~models.BuildTask.dependencies.any()
        db_task = await db.execute(
            select(models.BuildTask).where(query).with_for_update().filter(
                    sqlalchemy.and_(
                        models.BuildTask.status < BuildTaskStatus.COMPLETED,
                        models.BuildTask.arch.in_(request.supported_arches),
                        sqlalchemy.or_(
                            models.BuildTask.ts < ts_expired,
                            models.BuildTask.ts.__eq__(None)
                        )
                    )
                ).options(
                selectinload(models.BuildTask.ref),
                selectinload(models.BuildTask.build).selectinload(
                    models.Build.repos),
                selectinload(models.BuildTask.platform).selectinload(
                    models.Platform.repos),
                selectinload(models.BuildTask.build).selectinload(
                    models.Build.user),
                selectinload(models.BuildTask.build).selectinload(
                    models.Build.linked_builds).selectinload(
                    models.Build.repos)
            ).order_by(models.BuildTask.id)
        )
        db_task = db_task.scalars().first()
        if not db_task:
            return
        db_task.ts = datetime.datetime.now()
        db_task.status = BuildTaskStatus.STARTED
        await db.commit()
    return db_task


def add_build_task_dependencies(db: Session, task: models.BuildTask,
                                last_task: models.BuildTask):
    task.dependencies.append(last_task)


async def update_failed_build_items(db: Session, build_id: int):
    query = select(models.BuildTask).where(
        sqlalchemy.and_(
            models.BuildTask.build_id == build_id,
            models.BuildTask.status == BuildTaskStatus.FAILED)
    ).order_by(models.BuildTask.index, models.BuildTask.id)
    async with db.begin():
        last_task = None
        failed_tasks = await db.execute(query)
        for task in failed_tasks.scalars():
            task.status = BuildTaskStatus.IDLE
            if last_task is not None:
                await db.run_sync(add_build_task_dependencies, task, last_task)
            last_task = task
        await db.commit()


async def ping_tasks(
            db: Session,
            task_list: typing.List[int]
        ):
    query = models.BuildTask.id.in_(task_list)
    now = datetime.datetime.now()
    async with db.begin():
        await db.execute(update(models.BuildTask).where(query).values(ts=now))
        await db.commit()


async def build_done(
            db: Session,
            request: build_node_schema.BuildDone
        ):
    async with db.begin():
        query = models.BuildTask.id == request.task_id
        build_task = await db.execute(
            select(models.BuildTask).where(query).options(
                selectinload(models.BuildTask.build).selectinload(
                    models.Build.repos
                )
            ).with_for_update()
        )
        build_task = build_task.scalars().first()
        if BuildTaskStatus.is_finished(build_task.status):
            raise BuildError(f'Build task {build_task.id} already completed')
        status = BuildTaskStatus.COMPLETED
        if request.status == 'failed':
            status = BuildTaskStatus.FAILED
        elif request.status == 'excluded':
            status = BuildTaskStatus.EXCLUDED
        build_task.status = status
        remove_query = (
            models.BuildTaskDependency.c.build_task_dependency == request.task_id
        )
        await db.execute(
            delete(models.BuildTaskDependency).where(remove_query)
        )
        pulp_client = PulpClient(
            settings.pulp_host,
            settings.pulp_user,
            settings.pulp_password
        )
        artifacts = []
        for artifact in request.artifacts:
            href = None
            arch = build_task.arch
            if artifact.type == 'rpm' and artifact.arch == 'src':
                arch = artifact.arch
            repos = list(
                build_repo for build_repo in build_task.build.repos
                if build_repo.arch == arch
                and build_repo.type == artifact.type
                and build_repo.debug == artifact.is_debuginfo
            )
            if artifact.type == 'rpm':
                repo = repos[0]
                href = await pulp_client.create_rpm_package(
                    artifact.name, artifact.href, repo.pulp_href)
            elif artifact.type == 'build_log':
                repo = next(
                    repo for repo in repos
                    if repo.name.endswith(str(request.task_id))
                )
                href = await pulp_client.create_file(
                    artifact.name, artifact.href, repo.pulp_href)
            artifacts.append(
                models.BuildTaskArtifact(
                    build_task_id=build_task.id,
                    name=artifact.name,
                    type=artifact.type,
                    href=href
                )
            )
        db.add_all(artifacts)
        db.add(build_task)
        await db.commit()

    async with db.begin():
        rpms_result = await db.execute(select(models.BuildTaskArtifact).where(
            models.BuildTaskArtifact.build_task_id == build_task.id,
            models.BuildTaskArtifact.type == 'rpm'))
        srpm = None
        binary_rpms = []
        for rpm in rpms_result.scalars().all():
            if rpm.name.endswith('.src.rpm'):
                srpm = models.SourceRpm()
                srpm.artifact = rpm
                srpm.build = build_task.build
            else:
                binary_rpm = models.BinaryRpm()
                binary_rpm.artifact = rpm
                binary_rpm.build = build_task.build
                binary_rpms.append(binary_rpm)
        db.add(srpm)
        await db.commit()
    await db.refresh(srpm)
    for binary_rpm in binary_rpms:
        binary_rpm.source_rpm = srpm

    db.add_all(binary_rpms)
    await db.commit()


async def create_test_tasks(db: Session, build_task_id: int):
    pulp_client = PulpClient(
        settings.pulp_host,
        settings.pulp_user,
        settings.pulp_password
    )
    async with db.begin():
        build_task_query = await db.execute(
            select(models.BuildTask).where(
                models.BuildTask.id == build_task_id)
            .options(selectinload(models.BuildTask.artifacts))
        )
        build_task = build_task_query.scalars().first()

        latest_revision_query = select(
            func.max(models.TestTask.revision)).filter(
            models.TestTask.build_task_id == build_task_id)
        result = await db.execute(latest_revision_query)
        latest_revision = result.scalars().first()
        if latest_revision:
            new_revision = latest_revision + 1
        else:
            new_revision = 1

    # Create logs repository
    repo_name = f'test_logs-btid-{build_task.id}-tr-{new_revision}'
    repo_url, repo_href = await pulp_client.create_log_repo(
        repo_name, distro_path_start='test_logs')

    repository = models.Repository(
        name=repo_name, url=repo_url, arch=build_task.arch,
        pulp_href=repo_href, type='test_log', debug=False
    )
    async with db.begin():
        db.add(repository)
        await db.commit()

    async with db.begin():
        r_query = select(models.Repository).where(
            models.Repository.name == repo_name)
        results = await db.execute(r_query)
        repository = results.scalars().first()

    test_tasks = []
    for artifact in build_task.artifacts:
        if artifact.type != 'rpm':
            continue
        artifact_info = await pulp_client.get_rpm_package(
            artifact.href,
            include_fields=['name', 'version', 'release', 'arch']
        )
        task = models.TestTask(build_task_id=build_task_id,
                               package_name=artifact_info['name'],
                               package_version=artifact_info['version'],
                               env_arch=build_task.arch,
                               status=TestTaskStatus.CREATED,
                               revision=new_revision,
                               repository_id=repository.id)
        if artifact_info.get('release'):
            task.package_release = artifact_info['release']
        test_tasks.append(task)
    async with db.begin():
        db.add_all(test_tasks)
        await db.commit()


async def restart_build_tests(db: Session, build_id: int):
    async with db.begin():
        build_task_ids = await db.execute(
            select(models.BuildTask.id).where(
                models.BuildTask.build_id == build_id))
    for build_task_id in build_task_ids:
        await create_test_tasks(db, build_task_id[0])


async def complete_test_task(db: Session, task_id: int,
                             test_result: test_schema.TestTaskResult):
    pulp_client = PulpClient(
        settings.pulp_host,
        settings.pulp_user,
        settings.pulp_password
    )
    async with db.begin():
        tasks = await db.execute(select(models.TestTask).where(
            models.TestTask.id == task_id).options(
            selectinload(models.TestTask.repository)).with_for_update())
        task = tasks.scalars().first()
        status = TestTaskStatus.COMPLETED
        for key, item in test_result.result.items():
            if key == 'tests':
                for test_item in item.values():
                    if not test_item.get('success', False):
                        status = TestTaskStatus.FAILED
                        break
            # Skip logs from processing
            elif key == 'logs':
                continue
            elif not item.get('success', False):
                status = TestTaskStatus.FAILED
                break
        task.status = status
        task.alts_response = test_result.dict()
        logs = []
        for log in test_result.result.get('logs', []):
            if task.repository:
                href = await pulp_client.create_file(
                    log['name'], log['href'], task.repository.pulp_href)
            else:
                href = log['href']
            log_record = models.TestTaskArtifact(
                name=log['name'], href=href, test_task_id=task.id)
            logs.append(log_record)

        db.add(task)
        db.add_all(logs)
        await db.commit()


async def get_test_tasks_by_build_task(
        db: Session, build_task_id: int, latest: bool = True,
        revision: int = None):
    async with db.begin():
        query = select(models.TestTask).where(
            models.TestTask.build_task_id == build_task_id)
        # If latest=False, but revision is not set, should return
        # latest results anyway
        if (not latest and not revision) or latest:
            subquery = select(func.max(models.TestTask.revision)).filter(
                models.TestTask.build_task_id == build_task_id).scalar_subquery()
            query = query.filter(models.TestTask.revision == subquery)
        elif revision:
            query = query.filter(models.TestTask.revision == revision)
        result = await db.execute(query)
        return result.scalars().all()


async def github_login(
            db: Session,
            user: user_schema.LoginGithub
        ) -> models.User:
    async with db.begin():
        github_user_token = await get_user_github_token(
            user.code,
            settings.github_client,
            settings.github_client_secret
        )
        github_info = await get_github_user_info(github_user_token)
        if not any(item for item in github_info['organizations']
                   if item['login'] == 'AlmaLinux'):
            return
        new_user = models.User(
            username=github_info['login'],
            email=github_info['email']
        )
        query = models.User.username == new_user.username
        db_user = await db.execute(select(models.User).where(
            query).with_for_update())
        db_user = db_user.scalars().first()
        if not db_user:
            db.add(new_user)
            db_user = new_user
            await db.flush()
        db_user.github_token = github_user_token
        db_user.jwt_token = generate_JWT_token(
            {'user_id': db_user.id},
            settings.jwt_secret,
            settings.jwt_algorithm
        )
        await db.commit()
    await db.refresh(db_user)
    return db_user


async def get_user(
            db: Session,
            user_id: typing.Optional[int] = None,
            user_name: typing.Optional[str] = None,
            user_email: typing.Optional[str] = None
        ) -> models.User:
    query = models.User.id == user_id
    if user_name is not None:
        query = models.User.name == user_name
    elif user_email is not None:
        query = models.User.email == user_email
    db_user = await db.execute(select(models.User).where(query))
    return db_user.scalars().first()


async def get_releases(db: Session) -> typing.List[models.Release]:
    release_result = await db.execute(select(models.Release).options(
        selectinload(models.Release.created_by)))
    return release_result.scalars().all()


async def create_new_release(
            db: Session, user_id: int, payload: release_schema.ReleaseCreate
        ) -> models.Release:
    async with db.begin():
        user_q = select(models.User).where(models.User.id == user_id)
        user_result = await db.execute(user_q)
        platform_result = await db.execute(select(models.Platform).where(
            models.Platform.id.in_(
                (payload.platform_id, payload.reference_platform_id))))
        platforms = platform_result.scalars().all()
        base_platform = [item for item in platforms
                         if item.id == payload.platform_id][0]
        reference_platform = [item for item in platforms
                              if item.id == payload.reference_platform_id][0]

        user = user_result.scalars().first()
        new_release = models.Release()
        new_release.build_ids = payload.builds
        new_release.platform = base_platform
        new_release.plan = await get_release_plan(
            db, payload.builds, base_platform.name,
            base_platform.distr_version, reference_platform.name,
            reference_platform.distr_version
        )
        new_release.created_by = user
        db.add(new_release)
        await db.commit()

    await db.refresh(new_release)
    release_res = await db.execute(select(models.Release).where(
        models.Release.id == new_release.id).options(
        selectinload(models.Release.created_by),
        selectinload(models.Release.platform)
    ))
    return release_res.scalars().first()


async def update_release(
        db: Session, release_id: int,
        payload: release_schema.ReleaseUpdate
) -> models.Release:
    async with db.begin():
        release_result = await db.execute(select(models.Release).where(
            models.Release.id == release_id).with_for_update())
        release = release_result.scalars().first()
        if not release:
            raise DataNotFoundError(f'Release with ID {release_id} not found')
        if payload.plan:
            release.plan = payload.plan
        if payload.builds and payload.builds != release.build_ids:
            release.build_ids = payload.builds
            platform_result = await db.execute(select(models.Platform).where(
                models.Platform.id.in_(
                    (release.platform_id, release.reference_platform_id))))
            platforms = platform_result.scalars().all()
            base_platform = [item for item in platforms
                             if item.id == release.platform_id][0]
            reference_platform = [
                item for item in platforms
                if item.id == release.reference_platform_id][0]
            release.plan = await get_release_plan(
                db, payload.builds, base_platform.name,
                base_platform.distr_version, reference_platform.name,
                reference_platform.distr_version)
        db.add(release)
        await db.commit()
    await db.refresh(release)
    release_res = await db.execute(select(models.Release).where(
        models.Release.id == release.id).options(
        selectinload(models.Release.created_by),
        selectinload(models.Release.platform)
    ))
    return release_res.scalars().first()


async def commit_release(db: Session, release_id: int) -> (models.Release, str):
    async with db.begin():
        release_result = await db.execute(
            select(models.Release).where(
                models.Release.id == release_id).with_for_update()
        )
        release = release_result.scalars().first()
        if not release:
            raise DataNotFoundError(f'Release with ID {release_id} not found')
        builds_q = select(models.Build).where(
            models.Build.id.in_(release.build_ids))
        builds_result = await db.execute(builds_q)
        for build in builds_result.scalars().all():
            build.release = release
            db.add(build)
        release.status = ReleaseStatus.IN_PROGRESS
        db.add(release)
        await db.commit()
    try:
        await execute_release_plan(release_id, db)
    except (EmptyReleasePlan, MissingRepository) as e:
        message = f'Cannot commit release: {str(e)}'
        release.status = ReleaseStatus.FAILED
    else:
        message = 'Successfully committed release'
        release.status = ReleaseStatus.COMPLETED
    db.add(release)
    await db.commit()
    await db.refresh(release)
    release_res = await db.execute(select(models.Release).where(
        models.Release.id == release.id).options(
        selectinload(models.Release.created_by),
        selectinload(models.Release.platform)
    ))
    return release_res.scalars().first(), message


async def get_repositories(db: Session, repository_id: int = None
                           ) -> typing.List[models.Repository]:
    repo_q = select(models.Repository)
    if repository_id:
        repo_q = repo_q.where(models.Repository.id == repository_id)
    result = await db.execute(repo_q)
    return result.scalars().all()


async def create_repositories(
        db: Session,
        payload: typing.List[repository_schema.RepositoryCreate]
) -> typing.List[models.Repository]:
    # We need to update existing repositories instead of trying to create
    # new ones if they have the same parameters
    query_list = [
        sqlalchemy.and_(
            models.Repository.name == item.name,
            models.Repository.arch == item.arch,
            models.Repository.type == item.type
        )
        for item in payload
    ]
    query = sqlalchemy.or_(*query_list).with_for_update()
    repos_mapping = {}
    async with db.begin():
        repos_result = await db.execute(query)
        for repo in repos_result.scalars().all():
            repo_key = f'{repo.name}-{repo.arch}-{repo.debug}'
            repos_mapping[repo_key] = repo

        for repo_item in payload:
            repo_item_dict = repo_item.dict()
            repo_key = f'{repo_item.name}-{repo_item.arch}-{repo_item.debug}'
            if repo_key not in repos_mapping:
                repos_mapping[repo_key] = models.Repository(**repo_item_dict)
            else:
                repo = repos_mapping[repo_key]
                for field, value in repo_item_dict.items():
                    setattr(repo, field, value)

        db.add_all(repos_mapping.values())
        await db.commit()

    for repo in repos_mapping.values():
        await db.refresh(repo)

    return list(repos_mapping.values())


async def create_repository(
        db: Session, payload: repository_schema.RepositoryCreate
) -> models.Repository:
    query = select(models.Repository).where(
        models.Repository.name == payload.name,
        models.Repository.arch == payload.arch,
        models.Repository.type == payload.type,
        models.Repository.debug == payload.debug,
    )
    async with db.begin():
        result = await db.execute(query)
        if result.scalars().first():
            raise ValueError('Repository already exists')

        repository = models.Repository(**payload.dict())
        db.add(repository)
        await db.commit()
    await db.refresh(repository)
    return repository


async def update_repository(
        db: Session, repository_id: int,
        payload: repository_schema.RepositoryUpdate
) -> models.Repository:
    async with db.begin():
        result = await db.execute(select(models.Repository).where(
            models.Repository.id == repository_id))
        repository = result.scalars().first()
        for field, value in payload.dict():
            setattr(repository, field, value)
        db.add(repository)
        await db.commit()
    await db.refresh(repository)
    return repository


async def delete_repository(db: Session, repository_id: int):
    async with db.begin():
        await db.execute(delete(models.Repository).where(
            models.Repository.id == repository_id))
        await db.commit()


async def add_to_platform(db: Session, platform_id: int,
                          repository_ids: typing.List[int]) -> models.Platform:
    platform_result = await db.execute(select(models.Platform).where(
        models.Platform.id == platform_id).with_for_update())
    platform = platform_result.scalars().first()
    repositories_result = await db.execute(select(models.Repository).where(
        models.Repository.id.in_(repository_ids)))
    repositories = repositories_result.scalars().all()
    platform_repos_result = await db.execute(select(
        models.PlatformRepo.c.platform_id,
        models.PlatformRepo.c.repository_id).where(
        models.PlatformRepo.c.platform_id == platform_id,
        models.PlatformRepo.c.repository_id.in_(repository_ids)
    ))
    repos = platform_repos_result.scalars().all()
    platform_repo_ids = [item.id for item in
                         repos]
    for repo in repositories:
        if repo.id not in platform_repo_ids:
            platform_repo = models.PlatformRepo(
                repository_id=repo.id, platform_id=platform_id)
            db.add(platform_repo)

    platform.repos.append(repositories)
    db.add(platform)
    db.add_all(repositories)
    await db.commit()

    platform_result = await db.execute(select(models.Platform).where(
        models.Platform.id == platform_id).options(
        selectinload(models.Platform.repos)
    ))
    return platform_result.scalars().first()


async def remove_from_platform(
        db: Session, platform_id: int,
        repository_ids: typing.List[int]
) -> models.Platform:
    await db.execute(delete(models.PlatformRepo).where(
        models.PlatformRepo.c.platform_id == platform_id,
        models.PlatformRepo.c.repository_id.in_(repository_ids)
    ))
    await db.commit()

    platform_result = await db.execute(select(models.Platform).where(
        models.Platform.id == platform_id).options(
        selectinload(models.Platform.repos)
    ))
    return platform_result.scalars().first()


async def create_repository_remote(
        db: Session, payload: remote_schema.RemoteCreate
) -> models.RepositoryRemote:
    query = select(models.RepositoryRemote).where(
        models.RepositoryRemote.name == payload.name,
        models.RepositoryRemote.arch == payload.arch,
        models.RepositoryRemote.url == payload.url
    )
    pulp_client = PulpClient(
        settings.pulp_host,
        settings.pulp_user,
        settings.pulp_password
    )
    async with db.begin():
        result = await db.execute(query)
        if result.scalars().first():
            raise ValueError('Remote already exists')
        remote_href = await pulp_client.create_rpm_remote(
            payload.name, payload.url, remote_policy=payload.policy)
        remote = models.RepositoryRemote(
            name=payload.name,
            arch=payload.arch,
            url=payload.url,
            pulp_href=remote_href,
        )
        db.add(remote)
        await db.commit()
    await db.refresh(remote)
    return remote


async def update_repository_remote(
        db: Session, remote_id: int,
        payload: remote_schema.RemoteUpdate
) -> models.RepositoryRemote:
    query = select(models.RepositoryRemote).where(
        models.RepositoryRemote.id == remote_id)
    async with db.begin():
        result = await db.execute(query)
        remote = result.scalars().first()
        if not remote:
            raise ValueError('Remote not found')
        for key, value in payload.dict().items():
            setattr(remote, key, value)
        db.add(remote)
        await db.commit()
    await db.refresh(remote)
    return remote


async def sync_repo_from_remote(db: Session, repository_id: int,
                                payload: repository_schema.RepositorySync,
                                wait_for_result: bool = False):
    repo_q = select(models.Repository).where(
        models.Repository.id == repository_id)
    remote_q = select(models.RepositoryRemote).where(
        models.RepositoryRemote.id == payload.remote_id)
    async with db.begin():
        repo_result = await db.execute(repo_q)
        remote_result = await db.execute(remote_q)
        repository = repo_result.scalars().first()
        remote = remote_result.scalars().first()

    if not repository:
        raise ValueError('Repository not found')
    if not remote:
        raise ValueError('Remote not found')
    pulp_client = PulpClient(
        settings.pulp_host,
        settings.pulp_user,
        settings.pulp_password
    )
    return await pulp_client.sync_rpm_repo_from_remote(
        repository.pulp_href, remote.pulp_href,
        sync_policy=payload.sync_policy,
        wait_for_result=wait_for_result
    )

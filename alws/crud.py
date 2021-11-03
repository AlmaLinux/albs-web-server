import typing
import datetime
import collections

import sqlalchemy
from sqlalchemy import update, delete
from sqlalchemy.future import select
from sqlalchemy.orm import Session, selectinload
from sqlalchemy.sql.expression import func

from alws import models
from alws.errors import DataNotFoundError, BuildError, DistributionError, SignError
from alws.config import settings
from alws.utils.pulp_client import PulpClient
from alws.utils.github import get_user_github_token, get_github_user_info
from alws.utils.jwt_utils import generate_JWT_token
from alws.constants import BuildTaskStatus, TestTaskStatus, SignTaskStatus
from alws.build_planner import BuildPlanner
from alws.schemas import (
    build_schema, user_schema, platform_schema, build_task_schema,
    distro_schema, test_schema
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
        request: build_task_schema.BuildDone,
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
            build_artifact = build_task_schema.BuildDoneArtifact.from_orm(
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
    modify = collections.defaultdict(list)
    for task in db_build.tasks:
        for artifact in task.artifacts:
            if artifact.type != 'rpm':
                continue
            build_artifact = build_task_schema.TaskDoneArtifact.from_orm(
                artifact)
            for distro_repo in db_distro.repositories:
                if (distro_repo.arch == task.arch and
                        distro_repo.debug == build_artifact.is_debuginfo):
                    modify[distro_repo.pulp_href].append(artifact.href)
    for key, value in modify.items():
        if modification == 'add':
            await pulp_client.modify_repository(add=value, repo_to=key)
        else:
            await pulp_client.modify_repository(remove=value, repo_to=key)


async def sign_start(
            db: Session, 
            task_id: int,
            request: build_task_schema.RequestSignStart
        ) -> models.BuildTask:
    async with db.begin():
        ts_expired = datetime.datetime.now() - datetime.timedelta(minutes=20)
        query = models.BuildTask.id == task_id
        db_task = await db.execute(
            select(models.BuildTask).where(query).with_for_update().options(
                selectinload(models.BuildTask.build)
            )
        )
        db_task = db_task.scalars().first()
        if not db_task:
            return
        if not BuildTaskStatus.is_finished(db_task.status):
            raise SignError(f"Build task {db_task.id} isn't completed")
        db_task.build.pgp_key_id = request.pgp_key_id
        db_task.ts = datetime.datetime.now()
        db_task.sign_status = SignTaskStatus.STARTED
        await db.commit()
    return db_task


async def get_available_build_task(
            db: Session,
            request: build_task_schema.RequestSignTask
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


async def get_available_sign_task(
            db: Session,
            request: build_task_schema.RequestSignTask
        ) -> models.BuildTask:
    async with db.begin():
        # TODO: move minutes to config
        ts_expired = datetime.datetime.now() - datetime.timedelta(minutes=20)
        where_query = models.SignTask.has(
            models.SignTask.pgp_key_id.in_(request.pgp_keyids)
        )
        db_task = await db.execute(
            select(models.SignTask).where(where_query).with_for_update().filter(
                    sqlalchemy.and_(
                        models.SignTask.status < SignTaskStatus.COMPLETED,
                        sqlalchemy.or_(
                            models.BuildTask.ts < ts_expired,
                            models.BuildTask.ts.__eq__(None)
                        )
                    )
                ).options(
                    selectinload(models.SignTask.build_task).selectinload(
                        models.BuildTask.artifacts),
            ).order_by(models.SignTask.id)
        )
        db_task = db_task.scalars().first()
        if not db_task:
            return
        db_task.ts = datetime.datetime.now()
        db_task.sign_status = SignTaskStatus.STARTED
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
            request: build_task_schema.BuildDone
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


async def sign_done(
            db: Session,
            request: build_task_schema.SignDone
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
        if SignTaskStatus.is_finished(build_task.sign_status):
            raise SignError(f'Sign task {build_task.id} already completed')
        status = SignTaskStatus.COMPLETED
        if request.status == 'failed':
            status = SignTaskStatus.FAILED
        elif request.status == 'excluded':
            status = SignTaskStatus.EXCLUDED
        build_task.sign_status = status
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
            build_task.artifacts.delete()
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

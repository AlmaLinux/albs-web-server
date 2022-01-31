import re
import typing

import jmespath
from sqlalchemy.future import select
from sqlalchemy.orm import Session, selectinload

from alws import models
from alws.config import settings
from alws.constants import ReleaseStatus, RepoType
from alws.errors import DataNotFoundError, EmptyReleasePlan, MissingRepository
from alws.schemas import release_schema
from alws.utils.beholder_client import BeholderClient
from alws.utils.pulp_client import PulpClient


async def __get_pulp_packages(
        db: Session, build_ids: typing.List[int],
        build_tasks: typing.List[int] = None) \
        -> typing.Tuple[typing.List[dict], typing.List[str]]:
    src_rpm_names = []
    packages_fields = ['name', 'epoch', 'version', 'release', 'arch']
    pulp_packages = []
    pulp_client = PulpClient(
        settings.pulp_host,
        settings.pulp_user,
        settings.pulp_password
    )

    builds_q = select(models.Build).where(
        models.Build.id.in_(build_ids)).options(
        selectinload(
            models.Build.source_rpms).selectinload(
            models.SourceRpm.artifact),
        selectinload(
            models.Build.binary_rpms).selectinload(
            models.BinaryRpm.artifact)
    )
    build_result = await db.execute(builds_q)
    for build in build_result.scalars().all():
        for src_rpm in build.source_rpms:
            # Failsafe to not process logs
            if src_rpm.artifact.type != 'rpm':
                continue
            if build_tasks \
                    and src_rpm.artifact.build_task_id not in build_tasks:
                continue
            src_rpm_names.append(src_rpm.artifact.name)
            pkg_info = await pulp_client.get_rpm_package(
                src_rpm.artifact.href, include_fields=packages_fields)
            pkg_info['artifact_href'] = src_rpm.artifact.href
            pkg_info['full_name'] = src_rpm.artifact.name
            pulp_packages.append(pkg_info)
        for binary_rpm in build.binary_rpms:
            # Failsafe to not process logs
            if binary_rpm.artifact.type != 'rpm':
                continue
            if build_tasks \
                    and binary_rpm.artifact.build_task_id not in build_tasks:
                continue
            pkg_info = await pulp_client.get_rpm_package(
                binary_rpm.artifact.href, include_fields=packages_fields)
            pkg_info['artifact_href'] = binary_rpm.artifact.href
            pkg_info['full_name'] = binary_rpm.artifact.name
            pulp_packages.append(pkg_info)
    return pulp_packages, src_rpm_names


async def get_release_plan(db: Session, build_ids: typing.List[int],
                           base_dist_version: str,
                           reference_dist_name: str,
                           reference_dist_version: str,
                           build_tasks: typing.List[int] = None) -> dict:
    clean_ref_dist_name = re.search(
        r'(?P<dist_name>[a-z]+)', reference_dist_name,
        re.IGNORECASE).groupdict().get('dist_name')
    clean_ref_dist_name_lower = clean_ref_dist_name.lower()
    endpoint = f'/api/v1/distros/{clean_ref_dist_name}/' \
               f'{reference_dist_version}/projects/'
    packages = []
    repo_name_regex = re.compile(r'\w+-\d-(?P<name>\w+(-\w+)?)')
    pulp_packages, src_rpm_names = await __get_pulp_packages(
        db, build_ids, build_tasks=build_tasks)

    def get_pulp_based_response():
        return {
            'packages': [{'package': pkg, 'repositories': []}
                         for pkg in pulp_packages],
            'repositories': prod_repos
        }

    repo_q = select(models.Repository).where(
        models.Repository.production.is_(True))
    result = await db.execute(repo_q)
    prod_repos = [
        {
            'id': repo.id,
            'name': repo.name,
            'arch': repo.arch,
            'debug': repo.debug
        }
        for repo in result.scalars().all()
    ]

    repos_mapping = {RepoType(repo['name'], repo['arch'], repo['debug']): repo
                     for repo in prod_repos}

    if not settings.package_beholder_enabled:
        return get_pulp_based_response()

    beholder_response = await BeholderClient(settings.beholder_host).post(
        endpoint, src_rpm_names)
    if not beholder_response.get('packages'):
        return get_pulp_based_response()
    if beholder_response.get('packages', []):
        for package in pulp_packages:
            pkg_name = package['name']
            pkg_version = package['version']
            pkg_arch = package['arch']
            query = f'packages[].packages[?name==\'{pkg_name}\' ' \
                    f'&& version==\'{pkg_version}\' ' \
                    f'&& arch==\'{pkg_arch}\'][]'
            predicted_package = jmespath.search(query, beholder_response)
            pkg_info = {'package': package, 'repositories': []}
            if predicted_package:
                # JMESPath will find a list with 1 element inside
                predicted_package = predicted_package[0]
                repositories = predicted_package['repositories']
                release_repositories = set()
                for repo in repositories:
                    ref_repo_name = repo['name']
                    repo_name = (repo_name_regex.search(ref_repo_name)
                                 .groupdict()['name'])
                    release_repo_name = (f'{clean_ref_dist_name_lower}'
                                         f'-{base_dist_version}-{repo_name}')
                    debug = ref_repo_name.endswith('debuginfo')
                    if repo['arch'] == 'src':
                        debug = False
                    release_repo = RepoType(
                        release_repo_name, repo['arch'], debug)
                    release_repositories.add(release_repo)
                pkg_info['repositories'] = [
                    repos_mapping.get(item) for item in release_repositories]
            packages.append(pkg_info)
    return {
        'packages': packages,
        'repositories': prod_repos
    }


async def execute_release_plan(release_id: int, db: Session):
    packages_to_repo_layout = {}

    async with db.begin():
        release_result = await db.execute(
            select(models.Release).where(models.Release.id == release_id))
        release = release_result.scalars().first()
        if not release.plan.get('packages') or \
                not release.plan.get('repositories'):
            raise EmptyReleasePlan('Cannot execute plan with empty packages '
                                   'or repositories: {packages}, {repositories}'
                                   .format_map(release.plan))

    for package in release.plan['packages']:
        for repository in package['repositories']:
            repo_name = repository['name']
            repo_arch = repository['arch']
            if repo_name not in packages_to_repo_layout:
                packages_to_repo_layout[repo_name] = {}
            if repo_arch not in packages_to_repo_layout[repo_name]:
                packages_to_repo_layout[repo_name][repo_arch] = []
            packages_to_repo_layout[repo_name][repo_arch].append(
                package['package']['artifact_href'])

    pulp_client = PulpClient(
        settings.pulp_host,
        settings.pulp_user,
        settings.pulp_password
    )
    repo_status = {}

    for repository_name, arches in packages_to_repo_layout.items():
        repo_status[repository_name] = {}
        for arch, packages in arches.items():
            repo_q = select(models.Repository).where(
                models.Repository.name == repository_name,
                models.Repository.arch == arch)
            repo_result = await db.execute(repo_q)
            repo = repo_result.scalars().first()
            if not repo:
                raise MissingRepository(
                    f'Repository with name {repository_name} is missing '
                    f'or doesn\'t have pulp_href field')
            result = await pulp_client.modify_repository(
                repo.pulp_href, add=packages)
            repo_status[repository_name][arch] = result

    return repo_status


async def get_releases(db: Session) -> typing.List[models.Release]:
    release_result = await db.execute(select(models.Release).options(
        selectinload(models.Release.created_by),
        selectinload(models.Release.platform)))
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
        if getattr(payload, 'build_tasks', None):
            new_release.build_task_ids = payload.build_tasks
        new_release.platform = base_platform
        new_release.reference_platform_id = payload.reference_platform_id
        new_release.plan = await get_release_plan(
            db, payload.builds,
            base_platform.distr_version,
            reference_platform.name,
            reference_platform.distr_version,
            build_tasks=payload.build_tasks
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
        build_tasks = getattr(payload, 'build_tasks', None)
        if (payload.builds and payload.builds != release.build_ids) or \
                (build_tasks and build_tasks != release.build_task_ids):
            release.build_ids = payload.builds
            if build_tasks:
                release.build_task_ids = payload.build_tasks
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
                db, payload.builds,
                base_platform.distr_version,
                reference_platform.name,
                reference_platform.distr_version,
                build_tasks=payload.build_tasks
            )
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

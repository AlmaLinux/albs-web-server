import asyncio
from dataclasses import replace
from email.mime import base
import re
import copy
import typing
from collections import defaultdict

from sqlalchemy.future import select
from sqlalchemy.orm import Session, selectinload

from alws import models
from alws.config import settings
from alws.constants import ReleaseStatus, RepoType, PackageNevra
from alws.errors import (DataNotFoundError, EmptyReleasePlan,
                         MissingRepository, SignError)
from alws.schemas import release_schema
from alws.utils.beholder_client import BeholderClient
from alws.utils.debuginfo import is_debuginfo_rpm
from alws.utils.pulp_client import PulpClient
from alws.crud import sign_task
from alws.utils.modularity import IndexWrapper


async def __get_pulp_packages(
        db: Session, build_ids: typing.List[int],
        build_tasks: typing.List[int] = None) \
        -> typing.Tuple[typing.List[dict], typing.List[str], typing.List[dict]]:
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
            models.BinaryRpm.artifact),
        selectinload(models.Build.tasks).selectinload(
            models.BuildTask.rpm_module
        ),
        selectinload(models.Build.repos)
    )
    build_result = await db.execute(builds_q)
    modules_to_release = {}
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
            build_task = next(
                task
                for task in build.tasks
                if task.id == src_rpm.artifact.build_task_id
            )
            pkg_info['task_arch'] = build_task.arch
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
            build_task = next(
                task
                for task in build.tasks
                if task.id == binary_rpm.artifact.build_task_id
            )
            pkg_info['task_arch'] = build_task.arch
            pulp_packages.append(pkg_info)
        for task in build.tasks:
            if task.rpm_module and task.id in build_tasks:
                key = (
                    task.rpm_module.name,
                    task.rpm_module.stream,
                    task.rpm_module.version,
                    task.rpm_module.arch
                )
                if key in modules_to_release:
                    continue
                module_repo = next(
                    build_repo for build_repo in task.build.repos
                    if build_repo.arch == task.arch
                    and not build_repo.debug
                    and build_repo.type == 'rpm'
                )
                repo_modules_yaml = await pulp_client.get_repo_modules_yaml(
                    module_repo.url)
                module_index = IndexWrapper.from_template(repo_modules_yaml)
                for module in module_index.iter_modules():
                    modules_to_release[key] = {
                        'build_id': build.id,
                        'name': module.name,
                        'stream': module.stream,
                        'version': module.version,
                        'context': module.context,
                        'arch': module.arch,
                        'template': module.render()
                    }
    return pulp_packages, src_rpm_names, list(modules_to_release.values())


async def get_release_plan(db: Session, build_ids: typing.List[int],
                           base_platform: models.Platform,
                           reference_platform: models.Platform,
                           build_tasks: typing.List[int] = None) -> dict:
    packages = []
    rpm_modules = []
    beholder_cache = {}
    repo_name_regex = re.compile(r'\w+-\d-(?P<name>\w+(-\w+)?)')
    pulp_client = PulpClient(
        settings.pulp_host,
        settings.pulp_user,
        settings.pulp_password
    )
    pulp_packages, src_rpm_names, pulp_rpm_modules = await __get_pulp_packages(
        db, build_ids, build_tasks=build_tasks)

    async def check_package_presence_in_repo(pkgs_nevra: dict,
                                             repo_ver_href: str):
        params = {
            'name__in': ','.join(pkgs_nevra['name']),
            'epoch__in': ','.join(pkgs_nevra['epoch']),
            'version__in': ','.join(pkgs_nevra['version']),
            'release__in': ','.join(pkgs_nevra['release']),
            'arch': 'noarch',
            'repository_version': repo_ver_href,
            'fields': 'name,epoch,version,release,arch',
        }
        packages = await pulp_client.get_rpm_packages(params)
        if not packages:
            return
        repo_href = re.sub(r'versions\/\d+\/$', '', repo_ver_href)
        pkg_fullnames = [
            pkgs_mapping.get(PackageNevra(
                pkg['name'], pkg['epoch'], pkg['version'],
                pkg['release'], pkg['arch']
            ))
            for pkg in packages
        ]
        for fullname in filter(None, pkg_fullnames):
            existing_packages[fullname].append(
                repo_ids_by_href.get(repo_href, 0))

    async def prepare_and_execute_async_tasks() -> None:
        tasks = []
        for value in (True, False):
            pkg_dict = debug_pkgs_nevra if value else pkgs_nevra
            if not pkg_dict:
                continue
            for key in ('name', 'epoch', 'version', 'release'):
                pkg_dict[key] = set(pkg_dict[key])
            tasks.extend((
                check_package_presence_in_repo(pkg_dict, repo_href)
                for repo_href, repo_is_debug in latest_prod_repo_versions
                if repo_is_debug is value
            ))
        await asyncio.gather(*tasks)

    def prepare_data_for_executing_async_tasks(package: dict,
                                               full_name: str) -> None:
        pkg_name, pkg_epoch, pkg_version, pkg_release, pkg_arch = (
            package['name'], package['epoch'], package['version'],
            package['release'], package['arch']
        )
        nevra = PackageNevra(pkg_name, pkg_epoch, pkg_version,
                             pkg_release, pkg_arch)
        pkgs_mapping[nevra] = full_name
        if is_debuginfo_rpm(pkg_name):
            debug_pkgs_nevra['name'].append(pkg_name)
            debug_pkgs_nevra['epoch'].append(pkg_epoch)
            debug_pkgs_nevra['version'].append(pkg_version)
            debug_pkgs_nevra['release'].append(pkg_release)
        else:
            pkgs_nevra['name'].append(pkg_name)
            pkgs_nevra['epoch'].append(pkg_epoch)
            pkgs_nevra['version'].append(pkg_version)
            pkgs_nevra['release'].append(pkg_release)

    async def get_pulp_based_response():
        plan_packages = []
        for pkg in pulp_packages:
            full_name = pkg['full_name']
            if full_name in added_packages:
                continue
            if pkg['arch'] == 'noarch':
                prepare_data_for_executing_async_tasks(pkg, full_name)
            release_repo = repos_mapping[RepoType(
                '-'.join([
                    clean_ref_dist_name_lower,
                    base_platform.distr_version,
                    'devel'
                ]),
                pkg['task_arch'],
                False
            )]
            plan_packages.append({
                'package': pkg,
                'repositories': [release_repo]
            })
            added_packages.add(full_name)
        await prepare_and_execute_async_tasks()

        return {
            'packages': plan_packages,
            'repositories': prod_repos,
            'existing_packages': existing_packages,
            'modules': rpm_modules,
        }

    if not settings.package_beholder_enabled:
        return await get_pulp_based_response()

    clean_base_dist_name = re.search(
        r'(?P<dist_name>[a-z]+)', base_platform.name,
        re.IGNORECASE).groupdict().get('dist_name')
    if not clean_base_dist_name:
        raise ValueError(f'Base distribution name is malformed: '
                         f'{base_platform.name}')
    clean_base_dist_name_lower = clean_base_dist_name.lower()
    clean_ref_dist_name = re.search(
        r'(?P<dist_name>[a-z]+)', reference_platform.name,
        re.IGNORECASE).groupdict().get('dist_name')
    if not clean_ref_dist_name:
        raise ValueError(f'Reference distribution name is malformed: '
                         f'{reference_platform.name}')
    clean_ref_dist_name_lower = clean_ref_dist_name.lower()
    beholder = BeholderClient(settings.beholder_host)

    prod_repos = []
    tasks = []
    repo_ids_by_href = {}
    for repo in base_platform.repos:
        prod_repos.append({
            'id': repo.id,
            'name': repo.name,
            'arch': repo.arch,
            'debug': repo.debug,
            'url': repo.url,
        })
        tasks.append(pulp_client.get_repo_latest_version(repo.pulp_href,
                                                         for_releases=True))
        repo_ids_by_href[repo.pulp_href] = repo.id
    latest_prod_repo_versions = await asyncio.gather(*tasks)

    pkgs_mapping = {}
    repos_mapping = {
        RepoType(repo['name'], repo['arch'], repo['debug']): repo
        for repo in prod_repos
    }

    added_packages = set()
    pkgs_nevra, debug_pkgs_nevra, existing_packages = (
        defaultdict(list), defaultdict(list), defaultdict(list)
    )
    strong_arches = defaultdict(list)
    for weak_arch in base_platform.weak_arch_list:
        strong_arches[weak_arch['depends_on']].append(weak_arch['name'])

    for module in pulp_rpm_modules:
        module_arch_list = [module['arch']]
        for strong_arch, weak_arches in strong_arches.items():
            if module['arch'] in weak_arches:
                module_arch_list.append(strong_arch)
        endpoints = [
            f'/api/v1/distros/{dist_name}/'
            f'{reference_platform.distr_version}/module/{module["name"]}/'
            f'{module["stream"]}/{module_arch}/'
            for dist_name in [clean_ref_dist_name, base_platform.name]
            for module_arch in module_arch_list
        ]
        module_response = None
        for endpoint in endpoints:
            try:
                module_response = await beholder.get(endpoint)
            except Exception:
                pass
        module_info = {
            'module': module,
            'repositories': []
        }
        rpm_modules.append(module_info)
        if not module_response:
            continue
        for _packages in module_response['artifacts']:
            for pkg in _packages['packages']:
                key = (pkg['name'], pkg['version'], pkg['arch'])
                beholder_cache[key] = pkg
                for weak_arch in strong_arches[pkg['arch']]:
                    second_key = (
                        pkg['name'], pkg['version'], weak_arch
                    )
                    replaced_pkg = copy.deepcopy(pkg)
                    for repo in replaced_pkg['repositories']:
                        if repo['arch'] == pkg['arch']:
                            repo['arch'] = weak_arch
                    beholder_cache[second_key] = replaced_pkg
        module_repo = module_response['repository']
        repo_name = repo_name_regex.search(
            module_repo['name']).groupdict()['name']
        release_repo_name = '-'.join([
            clean_base_dist_name_lower,
            base_platform.distr_version,
            repo_name
        ])
        module_info['repositories'].append({
            'name': release_repo_name,
            'arch': module_repo['arch'],
            'debug': False
        })

    endpoint = f'/api/v1/distros/{clean_ref_dist_name}/' \
               f'{reference_platform.distr_version}/projects/'
    beholder_response = await beholder.post(endpoint, src_rpm_names)
    for pkg_list in beholder_response.get('packages', {}):
        for pkg in pkg_list['packages']:
            key = (pkg['name'], pkg['version'], pkg['arch'])
            beholder_cache[key] = pkg
            for weak_arch in strong_arches[pkg['arch']]:
                second_key = (
                    pkg['name'], pkg['version'], weak_arch
                )
                replaced_pkg = copy.deepcopy(pkg)
                for repo in replaced_pkg['repositories']:
                    if repo['arch'] == pkg['arch']:
                        repo['arch'] = weak_arch
                beholder_cache[second_key] = replaced_pkg
    if not beholder_cache:
        return await get_pulp_based_response()
    for package in pulp_packages:
        pkg_name = package['name']
        pkg_version = package['version']
        pkg_arch = package['arch']
        full_name = package['full_name']
        if full_name in added_packages:
            continue
        if pkg_arch == 'noarch':
            prepare_data_for_executing_async_tasks(package, full_name)
        key = (pkg_name, pkg_version, pkg_arch)
        predicted_package = beholder_cache.get(key, [])
        pkg_info = {'package': package, 'repositories': []}
        release_repositories = set()
        repositories = []
        if not predicted_package:
            continue
        repositories = predicted_package['repositories']
        for repo in repositories:
            ref_repo_name = repo['name']
            repo_name = (repo_name_regex.search(ref_repo_name)
                            .groupdict()['name'])
            release_repo_name = '-'.join([
                clean_ref_dist_name_lower,
                base_platform.distr_version,
                repo_name
            ])
            debug = ref_repo_name.endswith('debuginfo')
            if repo['arch'] == 'src':
                debug = False
            release_repo = RepoType(
                release_repo_name, repo['arch'], debug)
            release_repositories.add(release_repo)
        pkg_info['repositories'] = [
            repos_mapping.get(item) for item in release_repositories
        ]
        added_packages.add(full_name)
        packages.append(pkg_info)

    for package in pulp_packages:
        if package['full_name'] in added_packages:
            continue
        added_packages.add(package['full_name'])
        release_repo = repos_mapping[RepoType(
            '-'.join([
                clean_ref_dist_name_lower,
                base_platform.distr_version,
                'devel'
            ]),
            package['task_arch'],
            False
        )]
        pkg_info = {
            'package': package, 
            'repositories': [release_repo]
        }
        packages.append(pkg_info)

    # if noarch package already in repo with same NEVRA,
    # we should exclude this repo when generate release plan
    await prepare_and_execute_async_tasks()
    for pkg_info in packages:
        package = pkg_info['package']
        if package['arch'] != 'noarch':
            continue
        repos_ids = existing_packages.get(package['full_name'], [])
        # TODO: also add here check for build arches
        new_repos = [
            repo for repo in pkg_info['repositories']
            if repo['id'] not in repos_ids
        ]
        pkg_info['repositories'] = new_repos
    return {
        'packages': packages,
        'existing_packages': existing_packages,
        'modules': rpm_modules,
        'repositories': prod_repos
    }


async def execute_release_plan(release_id: int, db: Session):
    packages_to_repo_layout = {}

    async with db.begin():
        release_result = await db.execute(
            select(models.Release).where(
                models.Release.id == release_id).options(
                    selectinload(models.Release.platform)))
        release = release_result.scalars().first()
        if not release.plan.get('packages') or \
                not release.plan.get('repositories'):
            raise EmptyReleasePlan('Cannot execute plan with empty packages '
                                   'or repositories: {packages}, {repositories}'
                                   .format_map(release.plan))

    for build_id in release.build_ids:
        try:
            verified = await sign_task.verify_signed_build(
                db, build_id, release.platform.id)
        except (DataNotFoundError, ValueError, SignError) as e:
            msg = f'The build {build_id} was not verified, because\n{e}'
            raise SignError(msg)
        if not verified:
            msg = f'Cannot execute plan with wrong singing of {build_id}'
            raise SignError(msg)
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
    for module in release.plan.get('modules', []):
        for repository in module['repositories']:
            repo_name = repository['name']
            repo_arch = repository['arch']
            if repo_name not in packages_to_repo_layout:
                packages_to_repo_layout[repo_name] = {}
            if repo_arch not in packages_to_repo_layout[repo_name]:
                packages_to_repo_layout[repo_name][repo_arch] = []
            module_info = module['module']
            module_pulp_href, _ = await pulp_client.create_module(
                module_info['template'],
                module_info['name'],
                module_info['stream'],
                module_info['context'],
                module_info['arch']
            )
            packages_to_repo_layout[repo_name][repo_arch].append(
                module_pulp_href)

    repo_status = {}

    for repository_name, arches in packages_to_repo_layout.items():
        repo_status[repository_name] = {}
        for arch, packages in arches.items():
            repo_q = select(models.Repository).where(
                models.Repository.name == repository_name,
                models.Repository.arch == arch
            )
            repo_result = await db.execute(repo_q)
            repo = repo_result.scalars().first()
            if not repo:
                raise MissingRepository(
                    f'Repository with name {repository_name} is missing '
                    f'or doesn\'t have pulp_href field')
            result = await pulp_client.modify_repository(
                repo.pulp_href, add=packages)
            # after modify repos we need to publish repo content
            await pulp_client.create_rpm_publication(repo.pulp_href)
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
        platform_result = await db.execute(
            select(models.Platform).where(
                models.Platform.id.in_(
                    (payload.platform_id, payload.reference_platform_id)
                )
            ).options(selectinload(models.Platform.repos.and_(
                models.Repository.production == True  
            ))
        ))
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
            base_platform,
            reference_platform,
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
    except (EmptyReleasePlan, MissingRepository, SignError) as e:
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

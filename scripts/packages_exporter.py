import aiohttp
import argparse
import asyncio
import jmespath
import json
import logging
import os
import sys
import typing
import urllib.parse

from pathlib import Path
from plumbum import local
import sqlalchemy
from sqlalchemy.future import select
from sqlalchemy.orm import selectinload

sys.path.append(os.path.dirname(os.path.dirname(__file__)))


from alws import database
from alws import models
from alws.config import settings
from alws.routers.sign_key import get_sign_keys
from alws.utils.exporter import fs_export_repository
from alws.utils.pulp_client import PulpClient


HEADERS = {'Authorization': f'Bearer {settings.sign_server_token}'}


def parse_args():
    parser = argparse.ArgumentParser(
        'packages_exporter',
        description='Packages exporter script. Exports repositories from Pulp'
                    'and transfer them to production host'
    )
    parser.add_argument('-names', '--platform_names',
                        type=str, nargs='+', required=False,
                        help='List of platform names to export')
    parser.add_argument('-repos', '--repo_ids',
                        type=int, nargs='+', required=False,
                        help='List of repo ids to export')
    parser.add_argument('-a', '--arches', type=str, nargs='+',
                        required=False, help='List of arches to export')
    parser.add_argument('-id', '--release_id', type=int,
                        required=False, help='Extract repos by release_id')
    parser.add_argument('-v', '--verbose', action='store_true', default=False,
                        required=False, help='Enable verbose output')
    return parser.parse_args()


async def sign_repomd_xml(data):
    endpoint = 'sign-tasks/sync_sign_task/'
    url = urllib.parse.urljoin(settings.sign_server_url, endpoint)
    async with aiohttp.ClientSession(headers=HEADERS,
                                     raise_for_status=True) as session:
        async with session.post(url, json=data) as response:
            json_data = await response.read()
            json_data = json.loads(json_data)
            return json_data


async def get_sign_keys_from_db():
    async with database.Session() as session:
        return await get_sign_keys(session)


async def repomd_signer(export_path, key_id):
    with open(os.path.join(export_path, 'repomd.xml'), 'rt') as f:
        file_content = f.read()
    sign_data = {
        "content": file_content,
        "pgp_keyid": key_id,
    }
    result = await sign_repomd_xml(sign_data)
    result_data = result.get('asc_content')
    repodata_path = os.path.join(export_path, 'repomd.xml.asc')
    if result_data is not None:
        with open(repodata_path, 'w') as file:
            file.writelines(result_data)


async def copy_noarch_packages_from_x86_64_repo(
    source_repo_name: str,
    source_repo_href: str,
    destination_repo_name: str,
    destination_repo_href: str,
) -> None:
    async def retrieve_all_packages_from_pulp(
            latest_repo_version: str) -> list:
        endpoint = 'pulp/api/v3/content/rpm/packages/'
        params = {
            'arch': 'noarch',
            'fields': ','.join(('name', 'sha256', 'pulp_href')),
            'repository_version': latest_repo_version,
        }
        response = await pulp_client.request('GET', endpoint, params=params)
        packages = response['results']
        next_page = response.get('next')
        while next_page is not None:
            next_packages = await pulp_client.request('GET', next_page)
            packages.extend(next_packages['results'])
            next_page = next_packages.get('next')
        return packages

    pulp_client = PulpClient(
        settings.pulp_host,
        settings.pulp_user,
        settings.pulp_password,
    )
    # Get packages x86_64
    source_repo_packages = await retrieve_all_packages_from_pulp(
        await pulp_client.get_repo_latest_version(source_repo_href),
    )
    # Get packages ppc64le
    destination_repo_packages = await retrieve_all_packages_from_pulp(
        await pulp_client.get_repo_latest_version(destination_repo_href),
    )

    # compare packages
    packages_to_add = []
    added_package_names = []
    for package_dict in source_repo_packages:
        if package_dict not in destination_repo_packages:
            packages_to_add.append(package_dict['pulp_href'])
            added_package_names.append(package_dict['name'])

    # package transfer
    if packages_to_add:
        await pulp_client.modify_repository(destination_repo_href,
                                            add=packages_to_add)
        await pulp_client.create_rpm_publication(destination_repo_href)


async def prepare_and_execute_async_tasks(source_repo_dict: dict,
                                          destination_repo_dict: dict) -> None:
    tasks = []
    for repo_name, repo_href in source_repo_dict.items():
        dest_repo_name = repo_name.replace('x86_64', 'ppc64le')
        dest_repo_href = destination_repo_dict.get(dest_repo_name)
        if dest_repo_href is not None:
            tasks.append(copy_noarch_packages_from_x86_64_repo(
                source_repo_name=repo_name,
                source_repo_href=repo_href,
                destination_repo_name=dest_repo_name,
                destination_repo_href=dest_repo_href,
            ))
    await asyncio.gather(*tasks)



async def export_repos_from_pulp(platforms_dict: dict,
                                 platform_names: typing.List[str] = None,
                                 repo_ids: typing.List[int] = None,
                                 arches: typing.List[str] = None):

    where_conditions = models.Platform.is_reference.is_(False)
    if platform_names is not None:
        where_conditions = sqlalchemy.and_(
            models.Platform.name.in_(platform_names),
            models.Platform.is_reference.is_(False),
        )
    query = select(models.Platform).where(
        where_conditions).options(selectinload(models.Platform.repos))
    async with database.Session() as db:
        db_platforms = await db.execute(query)
    db_platforms = db_platforms.scalars().all()

    repo_ids_to_export = []
    repos_x86_64 = {}
    repos_ppc64le = {}
    for db_platform in db_platforms:
        platforms_dict[db_platform.id] = []
        for repo in db_platform.repos:
            if repo_ids is not None and repo.id not in repo_ids:
                continue
            if repo.production is True:
                if repo.arch == 'x86_64':
                    repos_x86_64[repo.name] = repo.pulp_href
                if repo.arch == 'ppc64le':
                    repos_ppc64le[repo.name] = repo.pulp_href
                if arches is not None:
                    if repo.arch in arches:
                        platforms_dict[db_platform.id].append(repo.export_path)
                        repo_ids_to_export.append(repo.id)
                else:
                    platforms_dict[db_platform.id].append(repo.export_path)
                    repo_ids_to_export.append(repo.id)
    await prepare_and_execute_async_tasks(repos_x86_64, repos_ppc64le)
    exported_paths = await fs_export_repository(
        db=db, repository_ids=set(repo_ids_to_export))
    return exported_paths


async def export_repos_from_release_plan(release_id: int):
    repo_ids = []
    async with database.Session() as db:
        db_release = await db.execute(
            select(models.Release).where(models.Release.id == release_id))
    db_release = db_release.scalars().first()

    repo_ids = jmespath.search('packages[].repositories[].id',
                               db_release.plan)
    repo_ids = set(repo_ids)
    async with database.Session() as db:
        db_repos = await db.execute(
            select(models.Repository).where(sqlalchemy.and_(
                models.Repository.id.in_(repo_ids),
                models.Repository.production.is_(True),
            ))
        )
    repos_x86_64 = {}
    repos_ppc64le = {}
    for db_repo in db_repos.scalars().all():
        if db_repo.arch == 'x86_64':
            repos_x86_64[db_repo.name] = db_repo.pulp_href
        if db_repo.arch == 'ppc64le':
            repos_ppc64le[db_repo.name] = db_repo.pulp_href
    await prepare_and_execute_async_tasks(repos_x86_64, repos_ppc64le)
    exported_paths = await fs_export_repository(db=db, repository_ids=repo_ids)
    return exported_paths, db_release.platform_id


async def delete_existing_exporters_from_pulp():
    deleted_exporters = []
    pulp_client = PulpClient(
        settings.pulp_host,
        settings.pulp_user,
        settings.pulp_password,
    )
    existing_exporters = await pulp_client.list_filesystem_exporters()
    for exporter in existing_exporters:
        await pulp_client.delete_filesystem_exporter(exporter['pulp_href'])
        deleted_exporters.append(exporter['name'])
    return deleted_exporters


async def main():
    args = parse_args()
    logger = logging.getLogger('packages-exporter')
    if args.verbose:
        logging.basicConfig(level=logging.DEBUG)
    else:
        logging.basicConfig(level=logging.INFO)

    platforms_dict = {}
    key_id_by_platform = None
    exported_paths = []

    deleted_exporters = await delete_existing_exporters_from_pulp()
    if deleted_exporters:
        logger.info('Following exporters, has been deleted from pulp:\n%s',
                    '\n'.join(str(i) for i in deleted_exporters))

    db_sign_keys = await get_sign_keys_from_db()
    if args.release_id:
        release_id = args.release_id
        logger.info('Start exporting packages from release id=%s',
                    release_id)
        exported_paths, platform_id = await export_repos_from_release_plan(
            release_id)
        key_id_by_platform = next((
            sign_key.keyid for sign_key in db_sign_keys
            if sign_key.platform_id == platform_id
        ), None)

    if args.platform_names or args.repo_ids:
        platform_names = args.platform_names
        repo_ids = args.repo_ids
        msg, msg_values = (
            'Start exporting packages for following platforms:\n%s',
            platform_names,
        )
        if repo_ids:
            msg, msg_values = (
                'Start exporting packages for following repositories:\n%s',
                repo_ids,
            )
        logger.info(msg, msg_values)
        exported_paths = await export_repos_from_pulp(
            platform_names=platform_names,
            platforms_dict=platforms_dict,
            arches=args.arches,
            repo_ids=repo_ids,
        )
    logger.info('All repositories exported in following paths:\n%s',
                '\n'.join((str(path) for path in exported_paths)))

    createrepo_c = local['createrepo_c']
    modifyrepo_c = local['modifyrepo_c']
    for exp_path in exported_paths:
        path = Path(exp_path)
        repo_path = path.parent
        repodata = repo_path / 'repodata'
        result = createrepo_c.run(
            args=['--update', '--keep-all-metadata', repo_path],
        )
        logger.info(result)
        key_id = key_id_by_platform or None
        for platform_id, platform_repos in platforms_dict.items():
            for repo_export_path in platform_repos:
                if repo_export_path in str(exp_path):
                    key_id = next((
                        sign_key.keyid for sign_key in db_sign_keys
                        if sign_key.platform_id == platform_id
                    ), None)
                    break
        if key_id is None:
            logger.info('Cannot sign repomd.xml in %s, missing GPG key',
                        str(exp_path))
            continue
        await repomd_signer(repodata, key_id)
        logger.info('repomd.xml in %s is signed', str(repodata))


if __name__ == '__main__':
    asyncio.run(main())

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
from alws.utils.pulp_client import PulpClient


def parse_args():
    parser = argparse.ArgumentParser(
        'packages_exporter',
        description='Packages exporter script. Exports repositories from Pulp'
                    'and transfer them to the filesystem'
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
    parser.add_argument(
        '-copy', '--copy_noarch_packages', action='store_true',
        default=False, required=False,
        help='Copy noarch packages from x86_64 repos into ppc64le',
    )
    return parser.parse_args()


class Exporter:
    def __init__(
        self,
        pulp_client,
        copy_noarch_packages,
    ):
        logging.basicConfig(level=logging.INFO)
        self.logger = logging.getLogger('packages-exporter')
        self.pulp_client = pulp_client
        self.createrepo_c = local['createrepo_c']
        self.copy_noarch_packages = copy_noarch_packages
        self.headers = {
            'Authorization': f'Bearer {settings.sign_server_token}',
        }

    async def make_request(self, method: str, endpoint: str,
                           params: dict = None, data: dict = None):
        full_url = urllib.parse.urljoin(settings.sign_server_url, endpoint)
        async with aiohttp.ClientSession(headers=self.headers,
                                         raise_for_status=True) as session:
            async with session.request(method, full_url,
                                       json=data, params=params) as response:
                json_data = await response.read()
                json_data = json.loads(json_data)
                return json_data

    async def sign_repomd_xml(self, data):
        endpoint = 'sign-tasks/sync_sign_task/'
        return await self.make_request('POST', endpoint, data=data)

    async def get_sign_keys(self):
        endpoint = 'sign-keys/'
        return await self.make_request('GET', endpoint)

    async def export_repositories(self, repo_ids: list):
        endpoint = 'repositories/exports/'
        return await self.make_request('POST', endpoint, data=repo_ids)

    async def repomd_signer(self, repodata_path, key_id):
        string_repodata_path = str(repodata_path)
        if key_id is None:
            self.logger.info('Cannot sign repomd.xml in %s, missing GPG key',
                             string_repodata_path)
            return

        with open(os.path.join(repodata_path, 'repomd.xml'), 'rt') as f:
            file_content = f.read()
        sign_data = {
            "content": file_content,
            "pgp_keyid": key_id,
        }
        result = await self.sign_repomd_xml(sign_data)
        result_data = result.get('asc_content')
        if result_data is None:
            self.logger.error('repomd.xml in %s is failed to sign:\n%s',
                              string_repodata_path, result['error'])
            return

        repodata_path = os.path.join(repodata_path, 'repomd.xml.asc')
        with open(repodata_path, 'w') as file:
            file.writelines(result_data)
        self.logger.info('repomd.xml in %s is signed', string_repodata_path)

    async def retrieve_all_packages_from_pulp(
        self,
        latest_repo_version: str
    ) -> list[dict]:
        endpoint = 'pulp/api/v3/content/rpm/packages/'
        params = {
            'arch': 'noarch',
            'fields': ','.join(('name', 'version', 'release',
                                'sha256', 'pulp_href')),
            'repository_version': latest_repo_version,
        }
        response = await self.pulp_client.request('GET', endpoint,
                                                  params=params)
        packages = response['results']
        next_page = response.get('next')
        while next_page is not None:
            next_packages = await self.pulp_client.request('GET', next_page)
            packages.extend(next_packages['results'])
            next_page = next_packages.get('next')
        return packages

    async def copy_noarch_packages_from_x86_64_repo(
        self,
        source_repo_name: str,
        source_repo_href: str,
        destination_repo_name: str,
        destination_repo_href: str,
    ) -> None:

        # Get packages x86_64
        source_repo_packages = await self.retrieve_all_packages_from_pulp(
            await self.pulp_client.get_repo_latest_version(source_repo_href),
        )
        # Get packages ppc64le
        destination_repo_packages = await self.retrieve_all_packages_from_pulp(
            await self.pulp_client.get_repo_latest_version(
                destination_repo_href))

        # Compare packages
        packages_to_add = []
        packages_to_remove = []
        for package_dict in source_repo_packages:
            pkg_name = package_dict['name']
            pkg_version = package_dict['version']
            pkg_release = package_dict['release']
            is_modular = '.module_el' in pkg_release
            full_name = f'{pkg_name}-{pkg_version}-{pkg_release}.noarch.rpm'
            compared_pkg = next((
                pkg for pkg in destination_repo_packages
                if all((pkg['name'] == pkg_name,
                        pkg['version'] == pkg_version,
                        pkg['release'] == pkg_release))
            ), None)
            if compared_pkg is None:
                if is_modular:
                    continue
                packages_to_add.append(package_dict['pulp_href'])
                self.logger.info('%s added from "%s" repo into "%s" repo',
                                 full_name, source_repo_name,
                                 destination_repo_name)
                continue
            if package_dict['sha256'] != compared_pkg['sha256']:
                packages_to_remove.append(compared_pkg['pulp_href'])
                packages_to_add.append(package_dict['pulp_href'])
                self.logger.info('%s replaced in "%s" repo from "%s" repo',
                                 full_name, destination_repo_name,
                                 source_repo_name)

        # package transfer
        if packages_to_add:
            await self.pulp_client.modify_repository(
                destination_repo_href,
                add=packages_to_add,
                remove=packages_to_remove,
            )
            await self.pulp_client.create_rpm_publication(
                destination_repo_href,
            )

    async def prepare_and_execute_async_tasks(
        self,
        source_repo_dict: dict,
        destination_repo_dict: dict,
    ) -> None:
        tasks = []
        if not self.copy_noarch_packages:
            self.logger.info('Skip copying noarch packages')
            return
        for repo_name, repo_href in source_repo_dict.items():
            dest_repo_name = repo_name.replace('x86_64', 'ppc64le')
            dest_repo_href = destination_repo_dict.get(dest_repo_name)
            if dest_repo_href is not None:
                tasks.append(self.copy_noarch_packages_from_x86_64_repo(
                    source_repo_name=repo_name,
                    source_repo_href=repo_href,
                    destination_repo_name=dest_repo_name,
                    destination_repo_href=dest_repo_href,
                ))
        self.logger.info('Start checking and copying noarch packages in repos')
        await asyncio.gather(*tasks)

    async def export_repos_from_pulp(
        self,
        platform_names: typing.List[str] = None,
        repo_ids: typing.List[int] = None,
        arches: typing.List[str] = None
    ) -> (list[str], dict):
        platforms_dict = {}
        msg, msg_values = (
            'Start exporting packages for following platforms:\n%s',
            platform_names,
        )
        if repo_ids:
            msg, msg_values = (
                'Start exporting packages for following repositories:\n%s',
                repo_ids,
            )
        self.logger.info(msg, msg_values)

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
                    repo_name = (f"{repo.name}-"
                                 f"{'debuginfo-' if repo.debug else ''}"
                                 f"{repo.arch}")
                    if repo.arch == 'x86_64':
                        repos_x86_64[repo_name] = repo.pulp_href
                    if repo.arch == 'ppc64le':
                        repos_ppc64le[repo_name] = repo.pulp_href
                    if arches is not None:
                        if repo.arch in arches:
                            platforms_dict[db_platform.id].append(
                                repo.export_path)
                            repo_ids_to_export.append(repo.id)
                    else:
                        platforms_dict[db_platform.id].append(repo.export_path)
                        repo_ids_to_export.append(repo.id)
        await self.prepare_and_execute_async_tasks(repos_x86_64, repos_ppc64le)
        exported_paths = await self.export_repositories(
            list(set(repo_ids_to_export)))
        self.logger.info('All repositories exported in following paths:\n%s',
                         '\n'.join((str(path) for path in exported_paths)))
        return exported_paths, platforms_dict

    async def export_repos_from_release(self,
                                        release_id: int) -> (list[str], int):
        self.logger.info('Start exporting packages from release id=%s',
                         release_id)
        repo_ids = []
        async with database.Session() as db:
            db_release = await db.execute(
                select(models.Release).where(models.Release.id == release_id))
        db_release = db_release.scalars().first()

        repo_ids = jmespath.search('packages[].repositories[].id',
                                   db_release.plan)
        repo_ids = list(set(repo_ids))
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
            repo_name = (f"{db_repo.name}-"
                         f"{'debuginfo-' if db_repo.debug else ''}"
                         f"{db_repo.arch}")
            if db_repo.arch == 'x86_64':
                repos_x86_64[repo_name] = db_repo.pulp_href
            if db_repo.arch == 'ppc64le':
                repos_ppc64le[repo_name] = db_repo.pulp_href
        await self.prepare_and_execute_async_tasks(repos_x86_64, repos_ppc64le)
        exported_paths = await self.export_repositories(repo_ids)
        return exported_paths, db_release.platform_id

    async def delete_existing_exporters_from_pulp(self):
        deleted_exporters = []
        existing_exporters = await self.pulp_client.list_filesystem_exporters()
        for exporter in existing_exporters:
            await self.pulp_client.delete_filesystem_exporter(
                exporter['pulp_href'])
            deleted_exporters.append(exporter['name'])
        if deleted_exporters:
            self.logger.info(
                'Following exporters, has been deleted from pulp:\n%s',
                '\n'.join(str(i) for i in deleted_exporters),
            )

    def regenerate_repo_metadata(self, repo_path):
        exit_code, stdout, stderr = self.createrepo_c.run(
            args=['--update', '--keep-all-metadata', repo_path],
        )
        self.logger.info(stdout)


async def main():
    args = parse_args()

    platforms_dict = {}
    key_id_by_platform = None
    exported_paths = []
    pulp_client = PulpClient(
        settings.pulp_host,
        settings.pulp_user,
        settings.pulp_password,
    )
    exporter = Exporter(
        pulp_client=pulp_client,
        copy_noarch_packages=args.copy_noarch_packages,
    )

    await exporter.delete_existing_exporters_from_pulp()

    db_sign_keys = await exporter.get_sign_keys()
    if args.release_id:
        release_id = args.release_id
        exported_paths, platform_id = await exporter.export_repos_from_release(
            release_id)
        key_id_by_platform = next((
            sign_key['keyid'] for sign_key in db_sign_keys
            if sign_key['platform_id'] == platform_id
        ), None)

    if args.platform_names or args.repo_ids:
        platform_names = args.platform_names
        repo_ids = args.repo_ids
        exported_paths, platforms_dict = await exporter.export_repos_from_pulp(
            platform_names=platform_names,
            arches=args.arches,
            repo_ids=repo_ids,
        )

    for exp_path in exported_paths:
        string_exp_path = str(exp_path)
        path = Path(exp_path)
        repo_path = path.parent
        repodata = repo_path / 'repodata'
        exporter.regenerate_repo_metadata(repo_path)
        key_id = key_id_by_platform or None
        for platform_id, platform_repos in platforms_dict.items():
            for repo_export_path in platform_repos:
                if repo_export_path in string_exp_path:
                    key_id = next((
                        sign_key['keyid'] for sign_key in db_sign_keys
                        if sign_key['platform_id'] == platform_id
                    ), None)
                    break
        await exporter.repomd_signer(repodata, key_id)


if __name__ == '__main__':
    asyncio.run(main())

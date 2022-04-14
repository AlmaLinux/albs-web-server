import aiohttp
import argparse
import asyncio
import json
import logging
import os
import sys
import typing
import urllib.parse
from pathlib import Path

import jmespath
from plumbum import local
import sqlalchemy
from sqlalchemy.future import select
from sqlalchemy.orm import selectinload
from syncer import sync

sys.path.append(os.path.dirname(os.path.dirname(__file__)))


from alws import database
from alws import models
from alws.config import settings
from alws.utils.pulp_client import PulpClient
from errata_migrator import update_updateinfo


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
        '-distr', '--distribution', type=str, required=False,
        help='Check noarch packages by distribution'
    )
    parser.add_argument(
        '-copy', '--copy_noarch_packages', action='store_true',
        default=False, required=False,
        help='Copy noarch packages from x86_64 repos into others',
    )
    parser.add_argument(
        '-show-differ', '--show_differ_packages', action='store_true',
        default=False, required=False,
        help='Shows only packages that have different checksum',
    )
    parser.add_argument('-check', '--only_check_noarch', action='store_true',
                        default=False, required=False,
                        help='Only check noarch packages without copying')
    return parser.parse_args()


class Exporter:
    def __init__(
        self,
        pulp_client,
        copy_noarch_packages,
        only_check_noarch,
        show_differ_packages,
    ):
        logging.basicConfig(level=logging.INFO)
        self.logger = logging.getLogger('packages-exporter')
        self.pulp_client = pulp_client
        self.createrepo_c = local['createrepo_c']
        self.modifyrepo_c = local['modifyrepo_c']
        self.copy_noarch_packages = copy_noarch_packages
        self.only_check_noarch = only_check_noarch
        self.show_differ_packages = show_differ_packages
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

    async def create_filesystem_exporters(
            self, repository_ids: typing.List[int],
            get_publications: bool = False
    ):

        export_data = []

        async with database.Session() as db:
            query = select(models.Repository).where(
                models.Repository.id.in_(repository_ids))
            result = await db.execute(query)
            repositories = list(result.scalars().all())

        for repo in repositories:
            export_path = str(Path(
                settings.pulp_export_path, repo.export_path, 'Packages'))
            exporter_name = f'{repo.name}-{repo.arch}-debug' if repo.debug \
                else f'{repo.name}-{repo.arch}'
            fs_exporter_href = await self.pulp_client.create_filesystem_exporter(
                exporter_name, export_path)

            repo_latest_version = await self.pulp_client.get_repo_latest_version(
                repo.pulp_href
            )
            repo_exporter_dict = {
                'repo_id': repo.id,
                'repo_latest_version': repo_latest_version,
                'exporter_name': exporter_name,
                'export_path': export_path,
                'exporter_href': fs_exporter_href
            }
            if get_publications:
                publications = self.pulp_client.get_rpm_publications(
                    repository_version_href=repo_latest_version,
                    include_fields=['pulp_href']
                )
                if publications:
                    publication_href = publications[0].get('pulp_href')
                    repo_exporter_dict['publication_href'] = publication_href

            export_data.append(repo_exporter_dict)
        return export_data

    async def sign_repomd_xml(self, data):
        endpoint = 'sign-tasks/sync_sign_task/'
        return await self.make_request('POST', endpoint, data=data)

    async def get_sign_keys(self):
        endpoint = 'sign-keys/'
        return await self.make_request('GET', endpoint)

    async def export_repositories(self, repo_ids: list) -> typing.List[str]:
        exporters = await self.create_filesystem_exporters(repo_ids)
        exported_paths = []
        for exporter in exporters:
            self.logger.info('Exporting repository using following data: %s',
                             str(exporter))
            export_path = exporter['export_path']
            exported_paths.append(export_path)
            href = exporter['exporter_href']
            repository_version = exporter['repo_latest_version']
            await self.pulp_client.export_to_filesystem(
                href, repository_version)
        return exported_paths

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
    ) -> typing.List[typing.Dict[str, str]]:
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
        while response.get('next'):
            new_url = response.get('next')
            parsed_url = urllib.parse.urlsplit(new_url)
            new_url = parsed_url.path + '?' + parsed_url.query
            response = await self.pulp_client.request('GET', new_url)
            packages.extend(response['results'])
        return packages

    async def copy_noarch_packages_from_x86_64_repo(
        self,
        source_repo_name: str,
        source_repo_packages: typing.List[dict],
        destination_repo_name: str,
        destination_repo_href: str,
    ) -> None:

        destination_repo_packages = await self.retrieve_all_packages_from_pulp(
            await self.pulp_client.get_repo_latest_version(
                destination_repo_href))

        packages_to_add = []
        packages_to_remove = []
        add_msg = '%s added from "%s" repo into "%s" repo'
        replace_msg = '%s replaced in "%s" repo from "%s" repo'
        if self.only_check_noarch:
            add_msg = '%s can be added from "%s" repo into "%s" repo'
            replace_msg = '%s can be replaced in "%s" repo from "%s" repo'
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
                if is_modular or self.show_differ_packages:
                    continue
                packages_to_add.append(package_dict['pulp_href'])
                self.logger.info(add_msg, full_name, source_repo_name,
                                 destination_repo_name)
                continue
            if package_dict['sha256'] != compared_pkg['sha256']:
                packages_to_remove.append(compared_pkg['pulp_href'])
                packages_to_add.append(package_dict['pulp_href'])
                self.logger.info(replace_msg, full_name, destination_repo_name,
                                 source_repo_name)

        if packages_to_add and not self.only_check_noarch:
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
        for source_repo_name, repo_href in source_repo_dict.items():
            source_is_debug = '-debug-' in source_repo_name
            source_repo_packages = await self.retrieve_all_packages_from_pulp(
                await self.pulp_client.get_repo_latest_version(repo_href),
            )
            for dest_repo_name, dest_repo_href in destination_repo_dict.items():
                dest_repo_is_debug = '-debug-' in dest_repo_name
                if source_is_debug != dest_repo_is_debug or (
                        '-src-' in dest_repo_name):
                    continue
                tasks.append(self.copy_noarch_packages_from_x86_64_repo(
                    source_repo_name=source_repo_name,
                    source_repo_packages=source_repo_packages,
                    destination_repo_name=dest_repo_name,
                    destination_repo_href=dest_repo_href,
                ))
        self.logger.info('Start checking and copying noarch packages in repos')
        await asyncio.gather(*tasks)

    async def export_repos_from_pulp(
        self,
        platform_names: typing.List[str] = None,
        repo_ids: typing.List[int] = None,
        distr_name: str = None,
        arches: typing.List[str] = None,
    ) -> typing.Tuple[typing.List[str], typing.Dict[int, str]]:
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
        if distr_name:
            query = select(models.Distribution).where(
                models.Distribution.name == distr_name,
            ).options(selectinload(models.Distribution.repositories))
        else:
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
        other_repos = {}
        for db_platform in db_platforms:
            platforms_dict[db_platform.id] = []
            if distr_name:
                repositories = db_platform.repositories
            else:
                repositories = db_platform.repos
            for repo in repositories:
                if repo_ids is not None and repo.id not in repo_ids:
                    continue
                if repo.production is True or bool(distr_name):
                    repo_name = (f"{repo.name}-"
                                 f"{'debuginfo-' if repo.debug else ''}"
                                 f"{repo.arch}")
                    if repo.arch == 'x86_64':
                        repos_x86_64[repo_name] = repo.pulp_href
                    else:
                        other_repos[repo_name] = repo.pulp_href
                    if arches is not None:
                        if repo.arch in arches:
                            platforms_dict[db_platform.id].append(
                                getattr(repo, 'export_path', None))
                            repo_ids_to_export.append(repo.id)
                    else:
                        platforms_dict[db_platform.id].append(
                            getattr(repo, 'export_path', None))
                        repo_ids_to_export.append(repo.id)
        await self.prepare_and_execute_async_tasks(repos_x86_64, other_repos)
        if self.only_check_noarch:
            return [], platforms_dict
        exported_paths = await self.export_repositories(
            list(set(repo_ids_to_export)))
        self.logger.info('All repositories exported in following paths:\n%s',
                         '\n'.join((str(path) for path in exported_paths)))
        return exported_paths, platforms_dict

    async def export_repos_from_release(
        self,
        release_id: int,
    ) -> typing.Tuple[typing.List[str], int]:
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
        _, stdout, _ = self.createrepo_c.run(
            args=['--update', '--keep-all-metadata', repo_path],
        )
        self.logger.info(stdout)

    def update_ppc64le_errata(self, repodata: Path):
        output_file = repodata / 'updateinfo.xml'
        input_repodata = Path(
            str(repodata).replace('ppc64le', 'x86_64')
        )
        input_updateinfo = list(input_repodata.glob('*updateinfo.xml*'))
        if input_updateinfo:
            input_updateinfo = input_updateinfo[0]
            update_updateinfo(
                str(input_updateinfo),
                str(repodata),
                str(output_file)
            )
            self.modifyrepo_c[
                '--mdtype=updateinfo', str(output_file), str(repodata)
            ].run()
            output_file.unlink()


def main():
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
        only_check_noarch=args.only_check_noarch,
        show_differ_packages=args.show_differ_packages,
    )

    sync(exporter.delete_existing_exporters_from_pulp())

    db_sign_keys = sync(exporter.get_sign_keys())
    if args.release_id:
        release_id = args.release_id
        exported_paths, platform_id = sync(exporter.export_repos_from_release(
            release_id))
        key_id_by_platform = next((
            sign_key['keyid'] for sign_key in db_sign_keys
            if sign_key['platform_id'] == platform_id
        ), None)

    if args.platform_names or args.repo_ids or args.distribution:
        platform_names = args.platform_names
        repo_ids = args.repo_ids
        exported_paths, platforms_dict = sync(exporter.export_repos_from_pulp(
            platform_names=platform_names,
            arches=args.arches,
            repo_ids=repo_ids,
            distr_name=args.distribution,
        ))

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
        if 'ppc64le' in exp_path:
            exporter.update_ppc64le_errata(repodata)
        sync(exporter.repomd_signer(repodata, key_id))


if __name__ == '__main__':
    main()

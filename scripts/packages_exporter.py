import aiohttp
import argparse
import asyncio
import json
import logging
import os
import sys
import typing
import urllib.parse
from concurrent.futures import as_completed, ThreadPoolExecutor
from pathlib import Path

import jmespath
import sqlalchemy
import rpm
import pgpy
from plumbum import local
from sqlalchemy.future import select
from sqlalchemy.orm import selectinload
from syncer import sync

sys.path.append(os.path.dirname(os.path.dirname(__file__)))


from alws import database
from alws import models
from alws.config import settings
from alws.constants import SignStatusEnum
from alws.utils.exporter import download_file, get_repodata_file_links
from alws.utils.pulp_client import PulpClient
from alws.utils.errata import (
    merge_errata_records, find_metadata, iter_updateinfo,
    extract_errata_metadata, extract_errata_metadata_modern,
    merge_errata_records_modern, generate_errata_page
)


KNOWN_SUBKEYS_CONFIG = os.path.abspath(os.path.expanduser(
    '~/config/known_subkeys.json'))


def parse_args():
    parser = argparse.ArgumentParser(
        'packages_exporter',
        description='Packages exporter script. Exports repositories from Pulp'
                    'and transfer them to the filesystem'
    )
    parser.add_argument('-names', '--platform-names',
                        type=str, nargs='+', required=False,
                        help='List of platform names to export')
    parser.add_argument('-repos', '--repo-ids',
                        type=int, nargs='+', required=False,
                        help='List of repo ids to export')
    parser.add_argument('-a', '--arches', type=str, nargs='+',
                        required=False, help='List of arches to export')
    parser.add_argument('-id', '--release-id', type=int,
                        required=False, help='Extract repos by release_id')
    parser.add_argument(
        '-distr', '--distribution', type=str, required=False,
        help='Check noarch packages by distribution'
    )
    parser.add_argument(
        '-copy', '--copy-noarch-packages', action='store_true',
        default=False, required=False,
        help='Copy noarch packages from x86_64 repos into others',
    )
    parser.add_argument(
        '-show-differ', '--show-differ-packages', action='store_true',
        default=False, required=False,
        help='Shows only packages that have different checksum',
    )
    parser.add_argument('-check', '--only-check-noarch', action='store_true',
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
        logging.basicConfig(
            format='%(asctime)s %(levelname)-8s %(message)s',
            level=logging.INFO,
            datefmt='%Y-%m-%d %H:%M:%S'
        )
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
        self.pulp_system_user = 'pulp'
        self.current_user = os.getlogin()
        self.export_error_file = os.path.abspath(
            os.path.expanduser('~/export.err'))
        if os.path.exists(self.export_error_file):
            os.remove(self.export_error_file)
        self.known_subkeys = {}
        if os.path.exists(KNOWN_SUBKEYS_CONFIG):
            with open(KNOWN_SUBKEYS_CONFIG, 'rt') as f:
                self.known_subkeys = json.load(f)

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
                'repo_url': repo.url,
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

    async def download_repodata(self, repodata_path, repodata_url):
        file_links = await get_repodata_file_links(repodata_url)
        for link in file_links:
            file_name = os.path.basename(link)
            self.logger.info('Downloading repodata from %s', link)
            await download_file(link, os.path.join(repodata_path, file_name))

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
            parent_dir = str(Path(export_path).parent)
            if not os.path.exists(parent_dir):
                self.logger.info('Repository %s directory is absent',
                                 exporter['exporter_name'])
                continue
            repodata_path = os.path.abspath(os.path.join(
                parent_dir, 'repodata'))
            repodata_url = urllib.parse.urljoin(
                exporter['repo_url'], 'repodata/')
            try:
                local['sudo']['chown',
                              f'{self.current_user}:{self.current_user}',
                              f'{parent_dir}'].run()
                if not os.path.exists(repodata_path):
                    os.makedirs(repodata_path)
                else:
                    local['sudo']['chown', '-R',
                                  f'{self.current_user}:{self.current_user}',
                                  f'{repodata_path}'].run()
                await self.download_repodata(repodata_path, repodata_url)
            except Exception as e:
                self.logger.error('Cannot download repodata file: %s', str(e))
            finally:
                local['sudo'][
                    'chown', '-R',
                    f'{self.pulp_system_user}:{self.pulp_system_user}',
                    repodata_path].run()
                local['sudo'][
                    'chown',
                    f'{self.pulp_system_user}:{self.pulp_system_user}',
                    parent_dir].run()
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
        for source_repo_name, repo_data in source_repo_dict.items():
            repo_href, source_is_debug = repo_data
            source_repo_packages = await self.retrieve_all_packages_from_pulp(
                await self.pulp_client.get_repo_latest_version(repo_href),
            )
            for dest_repo_name, dest_repo_data in destination_repo_dict.items():
                dest_repo_href, dest_repo_is_debug = dest_repo_data
                if source_is_debug != dest_repo_is_debug:
                    continue
                tasks.append(self.copy_noarch_packages_from_x86_64_repo(
                    source_repo_name=source_repo_name,
                    source_repo_packages=source_repo_packages,
                    destination_repo_name=dest_repo_name,
                    destination_repo_href=dest_repo_href,
                ))
        self.logger.info('Start checking and copying noarch packages in repos')
        await asyncio.gather(*tasks)

    @staticmethod
    def get_full_repo_name(repo: models.Repository) -> str:
        return f"{repo.name}-{'debuginfo-' if repo.debug else ''}{repo.arch}"

    async def check_noarch_in_user_distribution_repos(self, distr_name: str):
        async with database.Session() as db:
            db_distr = await db.execute(select(models.Distribution).where(
                models.Distribution.name == distr_name,
            ).options(selectinload(models.Distribution.repositories)))
        db_distr = db_distr.scalars().first()
        repos_x86_64 = {}
        other_repos = {}
        for repo in db_distr.repositories:
            if repo.arch == 'src':
                continue
            if repo.arch == 'x86_64':
                repos_x86_64[repo.name] = (repo.pulp_href, repo.debug)
            else:
                other_repos[repo.name] = (repo.pulp_href, repo.debug)
        await self.prepare_and_execute_async_tasks(repos_x86_64, other_repos)

    def check_rpms_signature(self, repository_path: str, sign_keys: list):
        self.logger.info('Checking signature for %s repo', repository_path)

        key_ids_lower = [i.keyid.lower() for i in sign_keys]
        ts = rpm.TransactionSet()
        ts.setVSFlags(rpm._RPMVSF_NOSIGNATURES)

        def check(pkg_path: str) -> typing.Tuple[SignStatusEnum, str]:
            if not os.path.exists(pkg_path):
                return SignStatusEnum.READ_ERROR, ''

            with open(pkg_path, 'rb') as fd:
                header = ts.hdrFromFdno(fd)
                signature = header[rpm.RPMTAG_SIGGPG]
                if not signature:
                    signature = header[rpm.RPMTAG_SIGPGP]
                if not signature:
                    return SignStatusEnum.NO_SIGNATURE, ''

                pgp_msg = pgpy.PGPMessage.from_blob(signature)
                for signature in pgp_msg.signatures:
                    sig = signature.signer.lower()
                    if sig in key_ids_lower:
                        return SignStatusEnum.SUCCESS, sig
                    else:
                        for key_id in key_ids_lower:
                            sub_keys = self.known_subkeys.get(key_id, [])
                            if sig in sub_keys:
                                return SignStatusEnum.SUCCESS, sig

                return SignStatusEnum.WRONG_SIGNATURE, sig

        errored_packages = set()
        no_signature_packages = set()
        wrong_signature_packages = set()
        futures = {}

        with ThreadPoolExecutor(max_workers=10) as executor:

            for package in os.listdir(repository_path):
                package_path = os.path.join(repository_path, package)
                if not package_path.endswith('.rpm'):
                    self.logger.debug('Skipping non-RPM file or directory: %s',
                                      package_path)
                    continue

                futures[executor.submit(check, package_path)] = package_path

            for future in as_completed(futures):
                package_path = futures[future]
                result, pkg_sig = future.result()
                if result == SignStatusEnum.READ_ERROR:
                    errored_packages.add(package_path)
                elif result == SignStatusEnum.NO_SIGNATURE:
                    no_signature_packages.add(package_path)
                elif result == SignStatusEnum.WRONG_SIGNATURE:
                    wrong_signature_packages.add(f'{package_path} {pkg_sig}')

        if errored_packages or no_signature_packages or wrong_signature_packages:
            if not os.path.exists(self.export_error_file):
                mode = 'wt'
            else:
                mode = 'at'
            lines = [f'Errors when checking packages in {repository_path}']
            if errored_packages:
                lines.append('Packages that we cannot get information about:')
                lines.extend(list(errored_packages))
            if no_signature_packages:
                lines.append('Packages without signature:')
                lines.extend(list(no_signature_packages))
            if wrong_signature_packages:
                lines.append('Packages with wrong signature:')
                lines.extend(list(wrong_signature_packages))
            lines.append('\n')
            with open(self.export_error_file, mode=mode) as f:
                f.write('\n'.join(lines))

        self.logger.info('Signature check is done')

    async def export_repos_from_pulp(
        self,
        platform_names: typing.List[str] = None,
        repo_ids: typing.List[int] = None,
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
        where_conditions = models.Platform.is_reference.is_(False)
        if platform_names is not None:
            where_conditions = sqlalchemy.and_(
                models.Platform.name.in_(platform_names),
                models.Platform.is_reference.is_(False),
            )
        query = select(models.Platform).where(
            where_conditions).options(
            selectinload(models.Platform.repos),
            selectinload(models.Platform.sign_keys)
        )
        async with database.Session() as db:
            db_platforms = await db.execute(query)
        db_platforms = db_platforms.scalars().all()

        repos_x86_64 = {}
        repos_ppc64le = {}
        final_export_paths = []
        for db_platform in db_platforms:
            repo_ids_to_export = []
            platforms_dict[db_platform.id] = []
            for repo in db_platform.repos:
                if (repo_ids is not None and repo.id not in repo_ids) or (
                        repo.production is False):
                    continue
                repo_name = self.get_full_repo_name(repo)
                if repo.arch == 'x86_64':
                    repos_x86_64[repo_name] = (repo.pulp_href, repo.debug)
                if repo.arch == 'ppc64le':
                    repos_ppc64le[repo_name] = (repo.pulp_href, repo.debug)
                if arches is not None:
                    if repo.arch in arches:
                        platforms_dict[db_platform.id].append(repo.export_path)
                        repo_ids_to_export.append(repo.id)
                else:
                    platforms_dict[db_platform.id].append(repo.export_path)
                    repo_ids_to_export.append(repo.id)
            exported_paths = await self.export_repositories(
                list(set(repo_ids_to_export)))
            final_export_paths.extend(exported_paths)
            for repo_path in exported_paths:
                if not os.path.exists(repo_path):
                    self.logger.error('Path %s does not exist', repo_path)
                    continue
                self.check_rpms_signature(repo_path, db_platform.sign_keys)
            self.logger.info('All repositories exported in following paths:\n%s',
                             '\n'.join((str(path) for path in exported_paths)))
        await self.prepare_and_execute_async_tasks(repos_x86_64, repos_ppc64le)
        return final_export_paths, platforms_dict

    async def export_repos_from_release(
        self,
        release_id: int,
    ) -> typing.Tuple[typing.List[str], int]:
        self.logger.info('Start exporting packages from release id=%s',
                         release_id)
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
            repo_name = self.get_full_repo_name(db_repo)
            if db_repo.arch == 'x86_64':
                repos_x86_64[repo_name] = (db_repo.pulp_href, db_repo.debug)
            if db_repo.arch == 'ppc64le':
                repos_ppc64le[repo_name] = (db_repo.pulp_href, db_repo.debug)
        await self.prepare_and_execute_async_tasks(repos_x86_64, repos_ppc64le)
        exported_paths = await self.export_repositories(repo_ids)
        return exported_paths, db_release.platform_id

    async def delete_existing_exporters_from_pulp(self):
        self.logger.info('Searching for existing exporters')
        deleted_exporters = []
        existing_exporters = await self.pulp_client.list_filesystem_exporters()
        for exporter in existing_exporters:
            try:
                await self.pulp_client.delete_filesystem_exporter(
                    exporter['pulp_href'])
                deleted_exporters.append(exporter['name'])
            except:
                self.logger.info('Exporter %s does not exist',
                                 exporter['name'])
        self.logger.info('Search for exporters is done')
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


async def sign_repodata(exporter: Exporter, exported_paths: typing.List[str],
                        platforms_dict: dict, db_sign_keys: list,
                        key_id_by_platform: str = None):

    repodata_paths = []

    tasks = []

    for repo_path in exported_paths:
        path = Path(repo_path)
        parent_dir = path.parent
        repodata = parent_dir / 'repodata'
        if not os.path.exists(repo_path):
            continue

        repodata_paths.append(repodata)

        key_id = key_id_by_platform or None
        for platform_id, platform_repos in platforms_dict.items():
            for repo_export_path in platform_repos:
                if repo_export_path in repo_path:
                    key_id = next((
                        sign_key['keyid'] for sign_key in db_sign_keys
                        if sign_key['platform_id'] == platform_id
                    ), None)
                    break

        local['sudo']['chown', '-R',
                      f'{exporter.current_user}:{exporter.current_user}',
                      f'{repodata}'].run()
        tasks.append(exporter.repomd_signer(repodata, key_id))

    await asyncio.gather(*tasks)

    for repodata_path in repodata_paths:
        local['sudo']['chown', '-R',
                      f'{exporter.current_user}:{exporter.current_user}',
                      f'{repodata_path}'].run()


def repo_post_processing(exporter: Exporter, repo_path: str):
    path = Path(repo_path)
    parent_dir = path.parent
    repodata = parent_dir / 'repodata'
    if not os.path.exists(repo_path):
        return

    result = True
    errata_records = []
    modern_errata_records = {'data': []}
    try:
        local['sudo']['chown',
                      f'{exporter.current_user}:{exporter.current_user}',
                      f'{parent_dir}'].run()
        local['sudo']['chown', '-R',
                      f'{exporter.current_user}:{exporter.current_user}',
                      f'{repodata}'].run()
        exporter.regenerate_repo_metadata(parent_dir)
        errata_file = find_metadata(str(repodata), 'updateinfo')
        for record in iter_updateinfo(errata_file):
            errata_records.append(extract_errata_metadata(record))
            modern_errata_records = merge_errata_records_modern(
                modern_errata_records,
                extract_errata_metadata_modern(record)
            )
    except Exception as e:
        exporter.logger.exception('Post-processing failed: %s', str(e))
        result = False
    finally:
        local['sudo']['chown', '-R',
                      f'{exporter.pulp_system_user}:{exporter.pulp_system_user}',
                      f'{repodata}'].run()
        local['sudo']['chown',
                      f'{exporter.pulp_system_user}:{exporter.pulp_system_user}',
                      f'{parent_dir}'].run()

    return result, errata_records, modern_errata_records


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
    if args.distribution:
        sync(exporter.check_noarch_in_user_distribution_repos(
            args.distribution))
        return
    sync(exporter.delete_existing_exporters_from_pulp())
    exporter.logger.info('Fixing permissions before export')
    local['sudo']['chown', '-R',
                  f'{exporter.pulp_system_user}:{exporter.pulp_system_user}',
                  f'{settings.pulp_export_path}'].run()
    exporter.logger.info('Permissions are fixed')

    db_sign_keys = sync(exporter.get_sign_keys())
    if args.release_id:
        release_id = args.release_id
        exported_paths, platform_id = sync(exporter.export_repos_from_release(
            release_id))
        key_id_by_platform = next((
            sign_key['keyid'] for sign_key in db_sign_keys
            if sign_key['platform_id'] == platform_id
        ), None)

    if args.platform_names or args.repo_ids:
        platform_names = args.platform_names
        repo_ids = args.repo_ids
        exported_paths, platforms_dict = sync(exporter.export_repos_from_pulp(
            platform_names=platform_names,
            arches=args.arches,
            repo_ids=repo_ids,
        ))

    try:
        local['sudo']['find', settings.pulp_export_path, '-type', 'f', '-name',
                      '*snippet', '-exec', 'rm', '-f', '{}', '+'].run()
    except Exception:
        pass

    errata_cache = []
    modern_errata_cache = {'data': []}
    for exp_path in exported_paths:
        result, errata_records, modern_errata_records = repo_post_processing(
            exporter, exp_path, errata_cache
        )
        if result:
            exporter.logger.info('%s post-processing is successful', exp_path)
        else:
            exporter.logger.error('%s post-processing has failed', exp_path)
        errata_cache = merge_errata_records(errata_cache, errata_records)
        modern_errata_cache = merge_errata_records_modern(
            modern_errata_cache, modern_errata_records
        )
    for item in errata_cache:
        item['issued_date'] = {'$date': int(item['issued_date'].timestamp() * 1000)}
        item['updated_date'] = {'$date': int(item['updated_date'].timestamp() * 1000)}

    sync(sign_repodata(exporter, exported_paths, platforms_dict, db_sign_keys,
                       key_id_by_platform=key_id_by_platform))

    if args.platform_names:
        exporter.logger.info('Starting export errata.json and oval.xml')
        errata_export_base_path = os.path.join(settings.pulp_export_path, 'errata')
        if not os.path.exists(errata_export_base_path):
            os.mkdir(errata_export_base_path)
        for platform in args.platform_names:
            platform_path = os.path.join(errata_export_base_path, platform)
            if not os.path.exists(platform_path):
                os.mkdir(platform_path)
            with open(os.path.join('errata.json'), 'w') as fd:
                json.dump(errata_cache, fd)
            with open(os.path.join('errata.full.json'), 'w') as fd:
                json.dump(modern_errata_cache, fd)
            html_path = os.path.join(platform_path, 'html')
            if not os.path.exists(html_path):
                os.mkdir(html_path)
            for record in errata_cache:
                generate_errata_page(record, html_path)


if __name__ == '__main__':
    main()

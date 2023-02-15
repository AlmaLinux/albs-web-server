import asyncio
import io
import json
import logging
import math
import re
import os
import typing
import urllib.parse
from typing import (
    Any,
    Dict,
    List,
)

import aiohttp
from aiohttp.client_exceptions import ClientResponseError
from fastapi import status
from aiohttp_retry import RetryClient, ExponentialRetry

from alws.constants import UPLOAD_FILE_CHUNK_SIZE
from alws.utils.file_utils import hash_content, hash_file
from alws.utils.ids import get_random_unique_version


PULP_SEMAPHORE = asyncio.Semaphore(5)


class PulpClient:

    def __init__(self, host: str, username: str, password: str):
        self._host = host
        self._username = username
        self._password = password
        self._auth = aiohttp.BasicAuth(self._username, self._password)
        self._current_transaction = None
        self._retry_options = ExponentialRetry(exceptions={
            asyncio.TimeoutError, ClientResponseError})

    async def create_log_repo(
            self, name: str, distro_path_start: str = 'build_logs') -> (str, str):
        ENDPOINT = 'pulp/api/v3/repositories/file/file/'
        payload = {'name': name, 'autopublish': True}
        response = await self.request('POST', ENDPOINT, json=payload)
        repo_href = response['pulp_href']
        await self.create_file_publication(repo_href)
        distro = await self.create_file_distro(
            name, repo_href, base_path_start=distro_path_start)
        return distro, repo_href

    async def create_rpm_repository(
            self, name, auto_publish: bool = False,
            create_publication: bool = False,
            base_path_start: str = 'builds') -> (str, str):
        endpoint = 'pulp/api/v3/repositories/rpm/rpm/'
        payload = {
            'name': name,
            'autopublish': auto_publish,
            'retain_repo_versions': 5,
        }
        response = await self.request('POST', endpoint, json=payload)
        repo_href = response['pulp_href']
        if create_publication:
            await self.create_rpm_publication(repo_href)
        distribution = await self.create_rpm_distro(
            name, repo_href, base_path_start=base_path_start)
        return distribution, repo_href

    async def create_build_rpm_repo(self, name: str) -> (str, str):
        return await self.create_rpm_repository(
            name, auto_publish=True, create_publication=True)

    async def get_repo_modules(self, repo_href: str) -> typing.List[str]:
        version = await self.get_by_href(repo_href)
        content = await self.get_latest_repo_present_content(
            version['latest_version_href'])
        if not content.get('rpm.modulemd', {}).get('href'):
            return []
        modules = await self.get_by_href(content['rpm.modulemd']['href'])
        return [module['pulp_href'] for module in modules.get('results', [])]

    async def get_by_href(self, href: str):
        return await self.request('GET', href)

    async def get_rpm_repository_by_params(
            self, params: dict) -> typing.Union[dict, None]:
        endpoint = 'pulp/api/v3/repositories/rpm/rpm/'
        response = await self.request('GET', endpoint, params=params)
        if response['count'] == 0:
            return None
        return response['results'][0]

    async def get_log_repository(self, name: str) -> typing.Union[dict, None]:
        endpoint = 'pulp/api/v3/repositories/file/file/'
        params = {'name': name}
        response = await self.request('GET', endpoint, params=params)
        if response['count'] == 0:
            return None
        return response['results'][0]

    async def get_log_distro(self, name: str) -> typing.Union[dict, None]:
        endpoint = 'pulp/api/v3/distributions/file/file/'
        params = {'name__contains': name}
        response = await self.request('GET', endpoint, params=params)
        if response['count'] == 0:
            return None
        return response['results'][0]

    async def get_rpm_repositories(
        self,
        params: dict,
    ) -> typing.Union[typing.List[dict], None]:
        endpoint = 'pulp/api/v3/repositories/rpm/rpm/'
        response = await self.request('GET', endpoint, params=params)
        if response['count'] == 0:
            return None
        return response['results']

    async def get_rpm_repository(self, name: str) -> typing.Union[dict, None]:
        endpoint = 'pulp/api/v3/repositories/rpm/rpm/'
        params = {'name': name}
        response = await self.request('GET', endpoint, params=params)
        if response['count'] == 0:
            return None
        return response['results'][0]

    async def get_rpm_distro(self, name: str) -> typing.Union[dict, None]:
        endpoint = 'pulp/api/v3/distributions/rpm/rpm/'
        params = {'name__contains': name}
        response = await self.request('GET', endpoint, params=params)
        if response['count'] == 0:
            return None
        return response['results'][0]

    async def get_rpm_distros(
        self,
        include_fields: typing.List[str] = None,
        exclude_fields: typing.List[str] = None,
        **search_params,
    ) -> typing.List[dict]:
        endpoint = "pulp/api/v3/distributions/rpm/rpm/"
        all_distros = []
        result = await self.__get_content_info(
            endpoint, include_fields=include_fields,
            exclude_fields=exclude_fields, **search_params)
        if result["count"] == 0:
            return []
        all_distros.extend(result["results"])
        while result.get("next"):
            new_url = result.get("next")
            parsed_url = urllib.parse.urlsplit(new_url)
            new_url = parsed_url.path + "?" + parsed_url.query
            result = await self.__get_content_info(
                new_url, include_fields=include_fields,
                exclude_fields=exclude_fields, **search_params)
            all_distros.extend(result["results"])
        return all_distros

    async def get_rpm_remote(self, name: str) -> typing.Union[dict, None]:
        endpoint = 'pulp/api/v3/remotes/rpm/rpm/'
        params = {'name__contains': name}
        response = await self.request('GET', endpoint, params=params)
        if response['count'] == 0:
            return None
        return response['results'][0]

    async def get_module_by_name_and_stream(
        self,
        name: str,
        stream: str,
    ) -> typing.Optional[typing.List[dict]]:
        endpoint = 'pulp/api/v3/content/rpm/modulemds/'
        params = {
            'name': name,
            'stream': stream
        }
        response = await self.request('GET', endpoint, params=params)
        if response['count'] == 0:
            return None
        return response['results']

    async def create_module_by_payload(self, payload: dict) -> str:
        ENDPOINT = 'pulp/api/v3/content/rpm/modulemds/'
        task = await self.request('POST', ENDPOINT, json=payload)
        task_result = await self.wait_for_task(task['task'])
        return task_result['created_resources'][0]

    async def create_module(self, content: str, name: str, stream: str,
                            context: str, arch: str):
        ENDPOINT = 'pulp/api/v3/content/rpm/modulemds/'
        artifact_href, sha256 = await self.upload_file(content)
        payload = {
            'relative_path': 'modules.yaml',
            'artifact': artifact_href,
            'name': name,
            'stream': stream,
            # Instead of real module version, we're inserting
            # mocked one, so we can update template in the future,
            # since pulp have this global index:
            # unique_together = ("name", "stream", "version", "context",
            #                    "arch")
            'version': get_random_unique_version(),
            'context': context,
            'arch': arch,
            'artifacts': [],
            'dependencies': []
        }
        task = await self.request('POST', ENDPOINT, json=payload)
        task_result = await self.wait_for_task(task['task'])
        return task_result['created_resources'][0], sha256

    async def check_if_artifact_exists(self, sha256: str) -> typing.Optional[str]:
        ENDPOINT = 'pulp/api/v3/artifacts/'
        payload = {
            'sha256': sha256
        }
        response = await self.request('GET', ENDPOINT, params=payload)
        if response['count']:
            return response['results'][0]['pulp_href']
        return None

    async def upload_comps(self, data: dict) -> typing.List[str]:
        """
        Endpoint will modify and publish repository after adding content units
        """
        endpoint = 'pulp/api/v3/rpm/comps/'
        task = await self.request('POST', endpoint, data=data)
        task_result = await self.wait_for_task(task['task'])
        return task_result['created_resources']

    async def _upload_local_file(self, file_path: str, sha256: str,
                                 chunk_size: int = UPLOAD_FILE_CHUNK_SIZE):
        file_size = os.path.getsize(file_path)
        chunks = math.ceil(file_size / chunk_size)
        start = 0
        upload_href = (await self.request(
            'POST', 'pulp/api/v3/uploads/', json={'size': file_size}
        ))['pulp_href']
        try:
            with open(file_path, 'rb') as f:
                for i in range(chunks):
                    chunk = io.BytesIO(f.read(chunk_size))
                    chunk.name = f'{file_path.strip("/").replace("/", "_")}_{i}'
                    payload = {'file': chunk}
                    if chunk_size >= file_size:
                        stop = file_size - 1
                    else:
                        stop = start + chunk_size - 1
                        if stop >= file_size:
                            stop = file_size - 1
                    headers = {
                        'Content-Range': f'bytes {start}-{stop}/{file_size}'
                    }
                    await self.request(
                        'PUT', upload_href, data=payload, headers=headers
                    )
                    start += chunk_size
        except Exception:
            logging.exception('Exception during the file upload', exc_info=True)
            await self.request('DELETE', upload_href, raw=True)
        else:
            task = await self.request(
                'POST', f'{upload_href}commit/', json={'sha256': sha256}
            )
            task_result = await self.wait_for_task(task['task'])
            return task_result['created_resources'][0]

    async def _upload_file(self, content, sha256):
        response = await self.request(
            'POST', 'pulp/api/v3/uploads/', json={'size': len(content)}
        )
        upload_href = response['pulp_href']
        if isinstance(content, str):
            content_fd = io.StringIO(content)
        else:
            content_fd = io.BytesIO(content)
        payload = {
            'file': content_fd
        }
        headers = {
            'Content-Range': f'bytes 0-{len(content) - 1}/{len(content)}'
        }
        await self.request(
            'PUT', upload_href, data=payload, headers=headers
        )
        task = await self.request(
            'POST', f'{upload_href}commit/', json={'sha256': sha256}
        )
        task_result = await self.wait_for_task(task['task'])
        return task_result['created_resources'][0]

    async def upload_file(self, content=None, file_path: str = None,
                          sha256: str = None):
        # Check content already exists
        if not sha256:
            if content:
                sha256 = hash_content(content)
            elif file_path:
                sha256 = hash_file(file_path, hash_type='sha256')

        if not sha256:
            raise ValueError('Cannot get SHA256 checksum for the upload')

        reference = await self.check_if_artifact_exists(sha256)

        # Return existing content
        if reference and sha256:
            return reference, sha256

        # Create new content
        if content:
            reference = await self._upload_file(content, sha256)
        elif file_path:
            reference = await self._upload_local_file(file_path, sha256)
        else:
            raise NotImplementedError('Other upload flows are not supported')

        return reference, sha256

    async def get_repo_modules_yaml(self, url: str):
        repomd_url = urllib.parse.urljoin(url, 'repodata/repomd.xml')
        async with aiohttp.ClientSession(auth=self._auth) as session:
            async with session.get(repomd_url) as response:
                repomd_xml = await response.text()
                response.raise_for_status()
            res = re.search(
                r'repodata/[\w\d]+-modules.yaml',
                repomd_xml
            )
            if not res:
                return
            modules_path = res.group()
            modules_url = urllib.parse.urljoin(url, modules_path)
            async with session.get(modules_url) as response:
                modules_yaml = await response.text()
                response.raise_for_status()
                return modules_yaml

    def begin(self):
        return self

    async def __aenter__(self):
        if self._current_transaction is not None:
            raise ValueError('Another transaction already in progress')
        self._current_transaction = {}

    async def __aexit__(self, exc_type, exc_value, exc_traceback):
        if exc_type is not None:
            await self.rollback()
        else:
            await self.commit()
        self._current_transaction = None

    async def rollback(self):
        # TODO: write description here, what should be done in rollback in real world
        pass

    async def commit(self):
        tasks = []
        for repo, payload in self._current_transaction.items():
            tasks.append(self._modify_repository(
                repo, list(payload['add']), list(payload['remove'])
            ))
        await asyncio.gather(*tasks)

    async def _update_transaction(
                self,
                repo_to: str,
                add: List[str] = None,
                remove: List[str] = None
            ):
        if not self._current_transaction.get(repo_to):
            self._current_transaction[repo_to] = {
                'add': set(),
                'remove': set(),
            }
        self._current_transaction[repo_to]['add'].update(add or [])
        self._current_transaction[repo_to]['remove'].update(remove or [])

    async def _modify_repository(
                self,
                repo_to: str,
                add: List[str] = None,
                remove: List[str] = None
            ):
        ENDPOINT = urllib.parse.urljoin(repo_to, 'modify/')
        payload = {}
        if add:
            payload['add_content_units'] = add
        if remove:
            payload['remove_content_units'] = remove
        task = await self.request('POST', ENDPOINT, json=payload)
        response = await self.wait_for_task(task['task'])
        return response

    async def modify_repository(
                self,
                repo_to: str,
                add: List[str] = None,
                remove: List[str] = None
            ) -> Dict[str, Any]:
        if self._current_transaction:
            return await self._update_transaction(repo_to, add, remove)
        return await self._modify_repository(repo_to, add, remove)

    async def create_file_publication(self, repository: str):
        ENDPOINT = 'pulp/api/v3/publications/file/file/'
        payload = {'repository': repository}
        task = await self.request('POST', ENDPOINT, json=payload)
        await self.wait_for_task(task['task'])

    async def create_rpm_publication(self, repository: str):
        # Creates repodata for repositories in some way
        ENDPOINT = 'pulp/api/v3/publications/rpm/rpm/'
        payload = {'repository': repository}
        task = await self.request('POST', ENDPOINT, json=payload)
        await self.wait_for_task(task['task'])

    async def create_file(
                self,
                file_name: str,
                artifact_href: str,
                repo: str = None,
            ) -> str:
        ENDPOINT = 'pulp/api/v3/content/file/files/'
        payload = {
            'relative_path': file_name,
            'artifact': artifact_href,
        }
        if repo:
            payload['repository'] = repo
        task = await self.request('POST', ENDPOINT, json=payload)
        task_result = await self.wait_for_task(task['task'])
        hrefs = [item for item in task_result['created_resources']
                 if 'file/files' in item]
        return hrefs[0] if hrefs else None

    async def create_rpm_package(
                self,
                package_name: str,
                artifact_href: str,
                repo: str = None
            ) -> typing.Optional[str]:
        ENDPOINT = 'pulp/api/v3/content/rpm/packages/'
        artifact_info = await self.get_artifact(
            artifact_href, include_fields=['sha256'])
        rpm_pkgs = await self.get_rpm_packages(
            include_fields=['pulp_href'], sha256=artifact_info['sha256'])
        if rpm_pkgs:
            return rpm_pkgs[0]['pulp_href']
        payload = {
            'relative_path': package_name,
            'artifact': artifact_href,
        }
        if repo:
            payload['repository'] = repo
        task = await self.request('POST', ENDPOINT, json=payload)
        task_result = await self.wait_for_task(task['task'])
        # Success case
        if task_result['state'] == 'completed':
            hrefs = [item for item in task_result['created_resources']
                     if 'rpm/packages' in item]
            return hrefs[0] if hrefs else None
        return None

    async def get_files(self, include_fields: typing.List[str] = None,
                        exclude_fields: typing.List[str] = None,
                        **params) -> list:
        endpoint = 'pulp/api/v3/content/file/files/'
        response = await self.__get_content_info(
            endpoint, include_fields=include_fields,
            exclude_fields=exclude_fields, **params)
        if response['count'] == 0:
            return []
        return list(response['results'])

    async def create_file_distro(self, name: str, repository: str,
                                 base_path_start: str = 'build_logs') -> str:
        ENDPOINT = 'pulp/api/v3/distributions/file/file/'
        payload = {
            'repository': repository,
            'name': f'{name}-distro',
            'base_path': f'{base_path_start}/{name}'
        }
        task = await self.request('POST', ENDPOINT, json=payload)
        task_result = await self.wait_for_task(task['task'])
        distro = await self.get_distro(task_result['created_resources'][0])
        return distro['base_url']

    async def get_latest_repo_present_content(self, repo_version: str) -> dict:
        repo_content = await self.get_by_href(repo_version)
        return repo_content['content_summary']['present']

    async def create_rpm_distro(self, name: str, repository: str,
                                base_path_start: str = 'builds') -> str:
        ENDPOINT = 'pulp/api/v3/distributions/rpm/rpm/'
        payload = {
            'repository': repository,
            'name': f'{name}-distro',
            'base_path': f'{base_path_start}/{name}'
        }
        task = await self.request('POST', ENDPOINT, json=payload)
        task_result = await self.wait_for_task(task['task'])
        distro = await self.get_distro(task_result['created_resources'][0])
        return distro['base_url']

    async def __get_content_info(self, endpoint,
                                 include_fields: typing.List[str] = None,
                                 exclude_fields: typing.List[str] = None,
                                 pure_url=False,
                                 **search_params):
        params = {}
        if include_fields:
            params['fields'] = include_fields
        if exclude_fields:
            params['exclude_fields'] = exclude_fields
        if search_params:
            params.update(**search_params)

        return await self.request('GET', endpoint, pure_url=pure_url,
                                  params=params)

    async def get_rpm_package(self, package_href,
                              include_fields: typing.List[str] = None,
                              exclude_fields: typing.List[str] = None):
        return await self.__get_content_info(
            package_href, include_fields=include_fields,
            exclude_fields=exclude_fields
        )

    async def get_rpm_packages(self, include_fields: typing.List[str] = None,
                               exclude_fields: typing.List[str] = None,
                               custom_endpoint: str = None,
                               **search_params):
        endpoint = 'pulp/api/v3/content/rpm/packages/'
        if custom_endpoint:
            endpoint = custom_endpoint
        all_rpms = []
        result = await self.__get_content_info(
            endpoint, include_fields=include_fields,
            exclude_fields=exclude_fields, **search_params)
        if result['count'] == 0:
            return []
        all_rpms.extend(result['results'])
        while result.get('next'):
            new_url = result.get('next')
            parsed_url = urllib.parse.urlsplit(new_url)
            new_url = parsed_url.path + '?' + parsed_url.query
            result = await self.__get_content_info(
                new_url, include_fields=include_fields,
                exclude_fields=exclude_fields, **search_params)
            all_rpms.extend(result['results'])
        return all_rpms

    async def get_rpm_repository_packages(
            self, repository_href: str,
            include_fields: typing.List[str] = None,
            exclude_fields: typing.List[str] = None,
            **search_params):
        latest_version = await self.get_repo_latest_version(repository_href)
        params = {'repository_version': latest_version, 'limit': 10000}
        params.update(**search_params)
        return await self.get_rpm_packages(
            include_fields=include_fields, exclude_fields=exclude_fields,
            **params
        )

    async def get_artifact(self, package_href,
                           include_fields: typing.List[str] = None,
                           exclude_fields: typing.List[str] = None):
        return await self.__get_content_info(
            package_href, include_fields=include_fields,
            exclude_fields=exclude_fields
        )

    async def delete_by_href(self, href: str, wait_for_result: bool = False):
        task = await self.request('DELETE', href)
        if wait_for_result:
            result = await self.wait_for_task(task['task'])
            return result
        return task

    async def create_rpm_remote(self, remote_name: str, remote_url: str,
                                remote_policy: str = 'on_demand') -> str:
        """
        Policy variants: 'on_demand', 'immediate', 'streamed'
        """
        ENDPOINT = 'pulp/api/v3/remotes/rpm/rpm/'
        payload = {
            'name': remote_name,
            'url': remote_url,
            'policy': remote_policy
        }
        result = await self.request('POST', ENDPOINT, json=payload)
        return result['pulp_href']

    async def update_rpm_remote(self, remote_href, remote_url: str,
                                remote_policy: str = 'on_demand') -> str:
        payload = {
            'url': remote_url,
            'policy': remote_policy
        }

        await self.request('PATCH', remote_href, data=payload)
        return remote_href

    async def sync_rpm_repo_from_remote(self, repo_href: str, remote_href: str,
                                        sync_policy: str = 'additive',
                                        wait_for_result: bool = False):
        """
        Policy variants: 'additive', 'mirror_complete', 'mirror_content_only'
        """
        endpoint = f'{repo_href}sync/'
        payload = {
            'remote': remote_href,
            'sync_policy': sync_policy
        }
        task = await self.request('POST', endpoint, json=payload)
        if wait_for_result:
            result = await self.wait_for_task(task['task'])
            return result
        return task

    async def find_filesystem_exporter(self, exporter_name: str):
        endpoint = 'pulp/api/v3/exporters/core/filesystem/'
        params = {'name': exporter_name}
        result = await self.request('GET', endpoint, params=params)
        if len(result['results']) == 0:
            return None
        return result['results'][0]

    async def create_filesystem_exporter(
            self, exporter_name: str, export_path: str,
            export_method: str = 'hardlink'):
        endpoint = 'pulp/api/v3/exporters/core/filesystem/'

        name = f'{exporter_name}-{export_method}'
        params = {
            'name': name,
            'path': export_path,
            'method': export_method
        }
        existing_exporter = await self.find_filesystem_exporter(name)
        if existing_exporter:
            if (existing_exporter['method'] != export_method
                    or existing_exporter['path'] != export_path):
                await self.update_filesystem_exporter(
                    existing_exporter['pulp_href'], name, export_path,
                    fse_method=export_method)
            return existing_exporter['pulp_href']
        result = await self.request('POST', endpoint, json=params)
        return result['pulp_href']

    async def update_filesystem_exporter(self, fse_pulp_href: str,
                                         fse_name: str,
                                         fse_path: str,
                                         fse_method: str = 'hardlink'):
        params = {
            'name': fse_name,
            'path': fse_path,
            'method': fse_method
        }
        update_task = await self.request('PUT', fse_pulp_href, data=params)
        task_result = await self.wait_for_task(update_task['task'])
        return task_result

    async def delete_filesystem_exporter(self, fse_pulp_href: str):
        delete_task = await self.request('DELETE', fse_pulp_href)
        task_result = await self.wait_for_task(delete_task['task'])
        return task_result

    async def list_filesystem_exporters(self):
        endpoint = 'pulp/api/v3/exporters/core/filesystem/'
        result = await self.request('GET', endpoint)
        if result['count'] > 0:
            return result['results']
        else:
            return []

    async def get_filesystem_exporter(self, fse_pulp_href: str):
        return await self.request('GET', fse_pulp_href)

    async def export_to_filesystem(self, fse_pulp_href: str,
                                   fse_repository_version: str):
        endpoint = urllib.parse.urljoin(fse_pulp_href, 'exports/')
        params = {
            'repository_version': fse_repository_version
        }
        fse_task = await self.request('POST', endpoint, json=params)
        await self.wait_for_task(fse_task['task'])
        return fse_repository_version

    async def get_repo_latest_version(
        self,
        repo_href: str,
    ) -> typing.Optional[str]:
        repository_data = await self.request('GET', repo_href)
        return repository_data.get('latest_version_href')

    async def iter_repo_packages(
        self,
        version_href: str,
        limit: int = 1000,
        fields=None,
        search_params: dict = None,
    ):
        payload = {'repository_version': version_href, 'limit': limit}
        if fields is not None:
            payload['fields'] = fields
        if search_params:
            payload.update(search_params)
        response = await self.request(
            'get', 'pulp/api/v3/content/rpm/packages/', params=payload
        )
        for pkg in response['results']:
            yield pkg
        while response.get('next'):
            parsed_next = urllib.parse.urlparse(response.get('next'))
            next_path = parsed_next.path + '?' + parsed_next.query
            response = await self.request('get', next_path)
            for pkg in response['results']:
                yield pkg

    async def get_rpm_publications(
            self, repository_version_href: str = None,
            include_fields: typing.List[str] = None,
            exclude_fields: typing.List[str] = None):
        endpoint = 'pulp/api/v3/publications/rpm/rpm/'
        params = {}
        if repository_version_href:
            params['repository_version'] = repository_version_href
        if include_fields:
            params['fields'] = include_fields
        if exclude_fields:
            params['exclude_fields'] = exclude_fields
        result = await self.request('GET', endpoint, params=params)
        if result['count'] == 0:
            return []
        return list(result['results'])

    async def get_distro(self, distro_href: str):
        return await self.request('GET', distro_href)

    async def create_entity(self, artifact):
        if artifact.type == 'rpm':
            entity_href = await self.create_rpm_package(
                artifact.name, artifact.href)
        else:
            entity_href = await self.create_file(
                artifact.name, artifact.href)
        info = await self.get_artifact(
            entity_href, include_fields=['sha256'])
        return entity_href, info['sha256'], artifact

    async def wait_for_task(self, task_href: str):
        task = await self.request('GET', task_href)
        while task['state'] not in ('failed', 'completed'):
            await asyncio.sleep(5)
            task = await self.request('GET', task_href)
        if task['state'] == 'failed':
            error = task.get('error')
            error_msg = ""
            if error:
                description = error.get('description', '')
                traceback = error.get('traceback', '')
                if description:
                    error_msg += f"\nDescription: {description}"
                if traceback:
                    error_msg += f"\nPulp traceback:\n{traceback}"
            raise Exception(
                f"Task {task['pulp_href']} has failed{error_msg}"
            )
        return task

    async def list_updateinfo_records(
                self,
                id__in: List[str],
                repository_version: typing.Optional[str] = None
            ):
        endpoint = 'pulp/api/v3/content/rpm/advisories/'
        payload = {
            'id__in': id__in
        }
        if repository_version:
            payload['repository_version'] = repository_version
        return (await self.request('GET', endpoint, params=payload))['results']

    async def add_errata_record(self, record: dict, repo_href: str):
        endpoint = 'pulp/api/v3/content/rpm/advisories/'
        payload = {
            'file': io.StringIO(json.dumps(record)),
            'repository': repo_href,
        }
        task = await self.request('POST', endpoint, data=payload)
        response = await self.wait_for_task(task['task'])
        return response

    async def add_errata_records(self, records: List[dict], repo_href: str):
        tasks = []
        for record in records:
            tasks.append(self.add_errata_record(record, repo_href))
        await asyncio.gather(*tasks)

    async def request(
        self, method: str, endpoint: str, pure_url: bool = False,
        params: dict = None, json: dict = None, data: dict = None,
        headers: dict = None, raw: bool = False
    ) -> dict:
        if pure_url:
            full_url = endpoint
        else:
            full_url = urllib.parse.urljoin(self._host, endpoint)
        async with PULP_SEMAPHORE:
            if method.lower() == 'get':
                async with RetryClient(
                        retry_options=self._retry_options) as client:
                    response = await client.get(
                        full_url, params=params, json=json, data=data,
                        headers=headers, auth=self._auth)
                    if raw:
                        return {'result': await response.text()}
                    response_json = await response.json()
            else:
                async with aiohttp.request(
                        method,
                        full_url,
                        params=params,
                        json=json,
                        data=data,
                        headers=headers,
                        auth=self._auth
                ) as response:
                    if raw:
                        return {'result': await response.text()}
                    response_json = await response.json()

            try:
                response.raise_for_status()
            except ClientResponseError as exc:
                if exc.status == status.HTTP_400_BAD_REQUEST:
                    exc.message += f": {str(response_json)}"
                raise exc
            return response_json

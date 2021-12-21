import io
import hashlib
import asyncio
import typing
import urllib.parse
from typing import Optional, List

import aiohttp

from alws.utils.modularity import ModuleWrapper, get_random_unique_version


PULP_SEMAPHORE = asyncio.Semaphore(10)


class PulpClient:

    def __init__(self, host: str, username: str, password: str):
        self._host = host
        self._username = username
        self._password = password
        self._auth = aiohttp.BasicAuth(self._username, self._password)

    async def create_log_repo(
            self, name: str, distro_path_start: str = 'build_logs') -> (str, str):
        ENDPOINT = 'pulp/api/v3/repositories/file/file/'
        payload = {'name': name, 'autopublish': True}
        response = await self.make_post_request(ENDPOINT, data=payload)
        repo_href = response['pulp_href']
        await self.create_file_publication(repo_href)
        distro = await self.create_file_distro(
            name, repo_href, base_path_start=distro_path_start)
        return distro, repo_href

    async def create_build_rpm_repo(self, name: str) -> str:
        ENDPOINT = 'pulp/api/v3/repositories/rpm/rpm/'
        payload = {'name': name, 'autopublish': True,
                   'retain_repo_versions': 1}
        response = await self.make_post_request(ENDPOINT, data=payload)

    async def create_rpm_repository(
            self, name, auto_publish: bool = False,
            create_publication: bool = False,
            base_path_start: str = 'builds') -> (str, str):
        endpoint = 'pulp/api/v3/repositories/rpm/rpm/'
        payload = {'name': name, 'autopublish': auto_publish}
        response = await self.make_post_request(endpoint, data=payload)
        repo_href = response['pulp_href']
        if create_publication:
            await self.create_rpm_publication(repo_href)
        distribution = await self.create_rpm_distro(
            name, repo_href, base_path_start=base_path_start)
        return distribution, repo_href

    async def create_build_rpm_repo(self, name: str) -> (str, str):
        return await self.create_rpm_repository(
            name, auto_publish=True, create_publication=True)

    async def get_rpm_repository(self, name: str) -> typing.Union[dict, None]:
        endpoint = 'pulp/api/v3/repositories/rpm/rpm/'
        params = {'name': name}
        response = await self.make_get_request(endpoint, params=params)
        if response['count'] == 0:
            return None
        return response['results'][0]

    async def get_rpm_distro(self, name: str) -> typing.Union[dict, None]:
        endpoint = 'pulp/api/v3/distributions/rpm/rpm/'
        params = {'name__contains': name}
        response = await self.make_get_request(endpoint, params=params)
        if response['count'] == 0:
            return None
        return response['results'][0]

    async def get_rpm_remote(self, name: str) -> typing.Union[dict, None]:
        endpoint = 'pulp/api/v3/remotes/rpm/rpm/'
        params = {'name__contains': name}
        response = await self.make_get_request(endpoint, params=params)
        if response['count'] == 0:
            return None
        return response['results'][0]

    async def create_module(self, content: str):
        ENDPOINT = 'pulp/api/v3/content/rpm/modulemds/'
        artifact_href, sha256 = await self.upload_file(content)
        module = ModuleWrapper.from_template(content)
        payload = {
            'relative_path': 'modules.yaml',
            'artifact': artifact_href,
            'name': module.name,
            'stream': module.stream,
            # Instead of real module version, we're inserting
            # mocked one, so we can update template in the future,
            # since pulp have this global index:
            # unique_together = ("name", "stream", "version", "context",
            #                    "arch")
            'version': get_random_unique_version(),
            'context': module.context,
            'arch': module.arch,
            'artifacts': [],
            'dependencies': []
        }
        task = await self.make_post_request(ENDPOINT, data=payload)
        task_result = await self.wait_for_task(task['task'])
        return task_result['created_resources'][0], sha256

    async def check_if_artifact_exists(self, sha256: str) -> str:
        ENDPOINT = 'pulp/api/v3/artifacts/'
        payload = {
            'sha256': sha256
        }
        response = await self.make_get_request(ENDPOINT, params=payload)
        if response['count']:
            return response['results'][0]['pulp_href']

    async def _upload_file(self, content, sha256):
        response = await self.make_post_request(
            'pulp/api/v3/uploads/', {'size': len(content)}
        )
        upload_href = response['pulp_href']
        payload = {
            'file': io.StringIO(content)
        }
        headers = {
            'Content-Range': f'bytes 0-{len(content) - 1}/{len(content)}'
        }
        await self.make_put_request(
            upload_href, data=payload, headers=headers
        )
        task = await self.make_post_request(
            f'{upload_href}commit/', data={'sha256': sha256}
        )
        task_result = await self.wait_for_task(task['task'])
        return task_result['created_resources'][0]

    # TODO: move this to utils, make it looks better
    def _hash_content(self, content):
        hasher = hashlib.new('sha256')
        hasher.update(content.encode())
        return hasher.hexdigest()

    async def upload_file(self, content=None):
        file_sha256 = self._hash_content(content)
        reference = await self.check_if_artifact_exists(file_sha256)
        if not reference:
            reference = await self._upload_file(content, file_sha256)
        return reference, file_sha256

    async def get_repo_modules_yaml(self, url: str, sha256: str):
        full_url = urllib.parse.urljoin(url, f'repodata/{sha256}-modules.yaml')
        async with aiohttp.ClientSession(auth=self._auth) as session:
            async with session.get(full_url) as response:
                text = await response.text()
                response.raise_for_status()
                return text

    async def modify_repository(self, repo_to: str, add: List[str] = None,
                                remove: List[str] = None):
        ENDPOINT = urllib.parse.urljoin(repo_to, 'modify/')
        payload = {}
        if add:
            payload['add_content_units'] = add
        if remove:
            payload['remove_content_units'] = remove
        task = await self.make_post_request(ENDPOINT, data=payload)
        response = await self.wait_for_task(task['task'])
        return response

    async def create_file_publication(self, repository: str):
        ENDPOINT = 'pulp/api/v3/publications/file/file/'
        payload = {'repository': repository}
        task = await self.make_post_request(ENDPOINT, data=payload)
        await self.wait_for_task(task['task'])

    async def create_rpm_publication(self, repository: str):
        ENDPOINT = 'pulp/api/v3/publications/rpm/rpm/'
        payload = {'repository': repository}
        task = await self.make_post_request(ENDPOINT, data=payload)
        await self.wait_for_task(task['task'])

    async def create_file(
                self,
                file_name: str,
                artifact_href: str,
                repo: str
            ) -> str:
        ENDPOINT = 'pulp/api/v3/content/file/files/'
        payload = {
            'relative_path': file_name,
            'artifact': artifact_href,
            'repository': repo
        }
        task = await self.make_post_request(ENDPOINT, data=payload)
        task_result = await self.wait_for_task(task['task'])
        hrefs = [item for item in task_result['created_resources']
                 if 'file/files' in item]
        return hrefs[0] if hrefs else None

    async def create_rpm_package(
                self,
                package_name: str,
                artifact_href: str,
                repo: str
            ) -> str:
        ENDPOINT = 'pulp/api/v3/content/rpm/packages/'
        payload = {
            'relative_path': package_name,
            'artifact': artifact_href,
            'repository': repo
        }
        task = await self.make_post_request(ENDPOINT, data=payload)
        task_result = await self.wait_for_task(task['task'])
        hrefs = [item for item in task_result['created_resources']
                 if 'rpm/packages' in item]
        return hrefs[0] if hrefs else None

    async def get_rpm_packages(self, params: dict = None) -> list:
        ENDPOINT = 'pulp/api/v3/content/rpm/packages/'
        response = await self.make_get_request(ENDPOINT, params=params)
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
        task = await self.make_post_request(ENDPOINT, data=payload)
        task_result = await self.wait_for_task(task['task'])
        distro = await self.get_distro(task_result['created_resources'][0])
        return distro['base_url']

    async def create_rpm_distro(self, name: str, repository: str,
                                base_path_start: str = 'builds') -> str:
        ENDPOINT = 'pulp/api/v3/distributions/rpm/rpm/'
        payload = {
            'repository': repository,
            'name': f'{name}-distro',
            'base_path': f'{base_path_start}/{name}'
        }
        task = await self.make_post_request(ENDPOINT, data=payload)
        task_result = await self.wait_for_task(task['task'])
        distro = await self.get_distro(task_result['created_resources'][0])
        return distro['base_url']

    async def get_rpm_package(self, package_href,
                              include_fields: typing.List[str] = None,
                              exclude_fields: typing.List[str] = None):
        params = {}
        if include_fields:
            params['fields'] = include_fields
        if exclude_fields:
            params['exclude_fields'] = exclude_fields
        return await self.make_get_request(package_href, params=params)

    async def remove_artifact(self, artifact_href: str,
                              need_wait_sync: bool=False):
        await self.make_delete_request(artifact_href)
        if need_wait_sync:
            remove_task = await self.get_distro(artifact_href)
            return remove_task

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
        result = await self.make_post_request(ENDPOINT, payload)
        return result['pulp_href']

    async def update_rpm_remote(self, remote_href, remote_url: str,
                                remote_policy: str = 'on_demand') -> str:
        payload = {
            'url': remote_url,
            'policy': remote_policy
        }
        await self.make_patch_request(remote_href, payload)
        return remote_href

    async def sync_rpm_repo_from_remote(self, repo_href: str, remote_href: str,
                                        sync_policy: str = 'additive',
                                        wait_for_result: bool = False):
        """
        Policy variants: 'additive', 'mirror_complete', 'mirror_content_only'
        """
        endpoint = f'{repo_href}sync/'
        if sync_policy == 'additive':
            mirror = False
        else:
            mirror = True
        payload = {
            'remote': remote_href,
            'mirror': mirror
        }
        task = await self.make_post_request(endpoint, payload)
        if wait_for_result:
            result = await self.wait_for_task(task['task'])
            return result
        return task

    async def create_filesystem_exporter(self, fse_name: str, fse_path: str,
                                         fse_method: str='write'):
        endpoint = 'pulp/api/v3/exporters/core/filesystem/'

        params = {
            'name': fse_name,
            'path': fse_path,
            'method': fse_method
        }
        result = await self.make_post_request(endpoint, params)
        return result['pulp_href']

    async def update_filesystem_exporter(self, fse_pulp_href: str,
                                         fse_name: str,
                                         fse_path: str,
                                         fse_method: str='symlink'):
        endpoint = fse_pulp_href
        params = {
            'name': fse_name,
            'path': fse_path,
            'method': fse_method
        }
        update_task = await self.make_put_request(endpoint, params)
        task_result = await self.wait_for_task(update_task['task'])
        return task_result

    async def delete_filesystem_exporter(self, fse_pulp_href: str):
        delete_task = await self.make_delete_request(fse_pulp_href)
        task_result = await self.wait_for_task(delete_task['task'])
        return task_result

    async def list_filesystem_exporters(self):
        endpoint = 'pulp/api/v3/exporters/core/filesystem/'
        result = await self.make_get_request(endpoint)
        if result['count'] > 0:
            return result['results']
        else:
            return []

    async def get_filesystem_exporter(self, fse_pulp_href : str):
        endpoint = fse_pulp_href
        result = await self.make_get_request(endpoint)
        return result

    async def export_to_filesystem(self, fse_pulp_href: str,
                                   fse_repository_version: str):
        endpoint = urllib.parse.urljoin(fse_pulp_href, 'exports/')
        params = {
            'repository_version': fse_repository_version
        }
        result = await self.make_post_request(endpoint, params)
        return result

    async def get_repo_latest_version(self, repo_href: str):
        repository_data = await self.make_get_request(repo_href)
        return repository_data.get('latest_version_href')

    async def get_distro(self, distro_href: str):
        return await self.make_get_request(distro_href)

    async def wait_for_task(self, task_href: str):
        task = await self.make_get_request(task_href)
        while task['state'] not in ('failed', 'completed'):
            await asyncio.sleep(0.3)
            task = await self.make_get_request(task_href)
        return task

    async def make_get_request(self, endpoint: str, params: dict = None):
        full_url = urllib.parse.urljoin(self._host, endpoint)
        async with aiohttp.ClientSession(auth=self._auth) as session:
            async with session.get(full_url, params=params) as response:
                json = await response.json(content_type=None)
                response.raise_for_status()
                return json

    async def make_post_request(self, endpoint: str, data: Optional[dict],
                                headers: Optional[dict] = None):
        full_url = urllib.parse.urljoin(self._host, endpoint)
        async with PULP_SEMAPHORE:
            async with aiohttp.ClientSession(auth=self._auth) as session:
                async with session.post(full_url, json=data, headers=headers) as response:
                    json = await response.json(content_type=None)
                    response.raise_for_status()
                    return json

    async def make_put_request(self, endpoint: str, data: Optional[dict],
                               headers: Optional[dict] = None):
        full_url = urllib.parse.urljoin(self._host, endpoint)
        async with PULP_SEMAPHORE:
            async with aiohttp.ClientSession(auth=self._auth) as session:
                async with session.put(full_url, data=data, headers=headers) as response:
                    json = await response.json(content_type=None)
                    response.raise_for_status()
                    return json

    async def make_patch_request(self, endpoint: str, data: Optional[dict],
                                 headers: Optional[dict] = None):
        full_url = urllib.parse.urljoin(self._host, endpoint)
        async with PULP_SEMAPHORE:
            async with aiohttp.ClientSession(auth=self._auth) as session:
                async with session.patch(full_url, data=data, headers=headers) as response:
                    json = await response.json(content_type=None)
                    response.raise_for_status()
                    return json

    async def make_delete_request(self, endpoint: str):
        full_url = urllib.parse.urljoin(self._host, endpoint)
        async with PULP_SEMAPHORE:
            async with aiohttp.ClientSession(auth=self._auth) as session:
                async with session.delete(full_url) as response:
                    json = await response.json(content_type=None)
                    return json

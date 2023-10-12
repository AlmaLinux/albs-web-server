import logging
import urllib.parse
from typing import List, Optional, Union

import aiohttp

from alws.constants import REQUEST_TIMEOUT

__all__ = ['AltsClient']


class AltsClient:
    def __init__(self, base_url: str, token: str):
        self._base_url = base_url
        self._headers = {'authorization': f'Bearer {token}'}
        self.__timeout = aiohttp.ClientTimeout(total=REQUEST_TIMEOUT)

    async def schedule_task(
        self,
        dist_name: str,
        dist_version: Union[int, str],
        dist_arch: str,
        package_name: str,
        package_version: str,
        callback_href: str,
        package_release: Optional[str] = None,
        repositories: Optional[List[dict]] = None,
        module_name: Optional[str] = None,
        module_stream: Optional[str] = None,
        module_version: Optional[str] = None,
        test_configuration: Optional[dict] = None,
    ):
        full_version = package_version
        if package_release:
            full_version = f'{package_version}-{package_release}'
        payload = {
            'runner_type': 'docker',
            'dist_name': dist_name,
            'dist_version': dist_version,
            'dist_arch': dist_arch,
            'package_name': package_name,
            'package_version': full_version,
            'callback_href': callback_href,
        }
        if module_name and module_stream and module_version:
            payload['module_name'] = module_name
            payload['module_stream'] = module_stream
            payload['module_version'] = module_version
        if repositories:
            payload['repositories'] = repositories
        if test_configuration:
            if test_configuration['tests'] is None:
                test_configuration['tests'] = []
            payload['test_configuration'] = test_configuration

        full_url = urllib.parse.urljoin(self._base_url, '/tasks/schedule')
        async with aiohttp.ClientSession(headers=self._headers) as session:
            async with session.post(
                full_url,
                json=payload,
                timeout=self.__timeout,
            ) as response:
                resp_json = None
                try:
                    resp_json = await response.json()
                except Exception as e:
                    logging.error(
                        'Cannot decode response from test system: %s', str(e)
                    )
                response.raise_for_status()
                return resp_json

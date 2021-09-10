import typing
import urllib.parse

import aiohttp


__all__ = ['AltsClient']


class AltsClient:
    def __init__(self, base_url: str, token: str):
        self._base_url = base_url
        self._headers = {'authorization': f'Bearer {token}'}

    async def schedule_task(self, dist_name: str,
                            dist_version: typing.Union[int, str],
                            dist_arch: str, package_name: str,
                            package_version: str, callback_href: str,
                            package_release: str = None,
                            repositories: typing.List[dict] = None):
        if package_release:
            full_version = f'{package_version}-{package_release}'
        else:
            full_version = package_version
        payload = {
            'runner_type': 'docker',
            'dist_name': dist_name,
            'dist_version': dist_version,
            'dist_arch': dist_arch,
            'package_name': package_name,
            'package_version': full_version,
            'callback_href': callback_href,
        }
        if repositories:
            payload['repositories'] = repositories

        full_url = urllib.parse.urljoin(self._base_url, '/tasks/schedule')
        async with aiohttp.ClientSession(headers=self._headers) as session:
            async with session.post(full_url, json=payload) as response:
                resp_json = await response.json()
                response.raise_for_status()
                return resp_json

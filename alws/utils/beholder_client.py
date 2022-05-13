import json
import typing
import urllib.parse

import aiohttp

from alws.constants import REQUEST_TIMEOUT
from alws.models import Platform
from alws.utils.parsing import get_clean_distr_name


class BeholderClient:
    def __init__(self, host: str, token: str = None):
        self._host = host
        self._headers = {}
        if token is not None:
            self._headers.update({
                'Authorization': f'Bearer {token}',
            })
        self.__timeout = aiohttp.ClientTimeout(total=REQUEST_TIMEOUT)

    @staticmethod
    def create_endpoints(
        platforms_list: typing.List[Platform],
        module_name: str = None,
        module_stream: str = None,
        module_arch_list: typing.List[str] = None,
    ) -> typing.Generator[None, None, str]:
        endpoints = (
            f'/api/v1/distros/{get_clean_distr_name(platform.name)}/'
            f'{platform.distr_version}/projects/'
            for platform in platforms_list
        )
        if module_name and module_stream and module_arch_list:
            endpoints = (
                f'/api/v1/distros/{get_clean_distr_name(platform.name)}/'
                f'{platform.distr_version}/module/{module_name}/'
                f'{module_stream}/{module_arch}/'
                for platform in platforms_list
                for module_arch in module_arch_list
            )
        return endpoints

    async def iter_endpoints(
        self,
        endpoints: typing.Iterable[str],
        is_module: bool = False,
        data: typing.Union[dict, list] = None,
    ) -> typing.Generator[dict, None, None]:
        for endpoint in endpoints:
            try:
                if is_module:
                    response = await self.get(endpoint)
                else:
                    response = await self.post(endpoint, data)
                yield response
            except Exception:
                pass

    async def retrieve_responses(
        self,
        platform: Platform,
        module_name: str = None,
        module_stream: str = None,
        module_arch_list: typing.List[str] = None,
        is_module: bool = False,
        data: typing.Union[dict, list] = None,
    ) -> typing.List[dict]:
        platforms_list = platform.reference_platforms + [platform]
        endpoints = self.create_endpoints(
            platforms_list,
            module_name,
            module_stream,
            module_arch_list,
        )
        responses = []
        async for response in self.iter_endpoints(endpoints, is_module, data):
            response_distr_name = response['distribution']['name']
            response_distr_ver = response['distribution']['version']
            response['priority'] = next(
                db_platform.priority for db_platform in platforms_list
                if db_platform.name.startswith(response_distr_name)
                and db_platform.distr_version == response_distr_ver
            )
            # we have priority only in ref platforms
            if response['priority'] is None:
                response['priority'] = 10
            responses.append(response)
        return sorted(responses, key=lambda x: x['priority'], reverse=True)

    def _get_url(self, endpoint: str) -> str:
        return urllib.parse.urljoin(self._host, endpoint)

    async def get(self, endpoint: str,
                  headers: dict = None, params: dict = None):
        req_headers = self._headers.copy()
        if headers:
            req_headers.update(**headers)
        full_url = self._get_url(endpoint)
        async with aiohttp.ClientSession(headers=req_headers,
                                         raise_for_status=True) as session:
            async with session.get(full_url, params=params,
                                   timeout=self.__timeout) as response:
                data = await response.read()
                json_data = json.loads(data)
                return json_data

    async def post(self, endpoint: str, data: typing.Union[dict, list]):
        async with aiohttp.ClientSession(headers=self._headers,
                                         raise_for_status=True) as session:
            async with session.post(
                    self._get_url(endpoint), json=data,
                    timeout=self.__timeout) as response:
                data = await response.read()
                json_data = json.loads(data)
                return json_data

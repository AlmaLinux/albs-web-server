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
    ) -> typing.Generator[None, None, typing.Tuple[str, int]]:
        endpoints = (
            (f'/api/v1/distros/{get_clean_distr_name(platform.name)}/'
             f'{platform.distr_version}/projects/',
             getattr(platform, 'priority', 10))
            for platform in platforms_list
        )
        if any((module_name, module_stream, module_arch_list)):
            endpoints = (
                (f'/api/v1/distros/{get_clean_distr_name(platform.name)}/'
                 f'{platform.distr_version}/module/{module_name}/'
                 f'{module_stream}/{module_arch}/',
                 getattr(platform, 'priority', 10))
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
        for endpoint, priority in endpoints:
            try:
                if is_module:
                    response = await self.get(endpoint)
                else:
                    response = await self.post(endpoint, data)
                response['is_beta'] = '-beta' in endpoint
                response['priority'] = priority
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
        async def _get_responses():
            return [
                response
                async for response in self.iter_endpoints(
                    endpoints, is_module, data)
            ]

        endpoints = self.create_endpoints(
            platform.reference_platforms,
            module_name,
            module_stream,
            module_arch_list,
        )
        responses = await _get_responses()
        if not responses:
            endpoints = self.create_endpoints(
                [platform],
                module_name,
                module_stream,
                module_arch_list,
            )
            responses = await _get_responses()
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

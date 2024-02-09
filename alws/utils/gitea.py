import asyncio
import typing
import urllib.parse
import logging

import aiohttp


class ModulesYamlNotFoundError(Exception):
    pass


def modules_yaml_path_from_url(url: str, ref: str, ref_type: str) -> str:
    repo_name = urllib.parse.urlparse(url).path.split('/')[-1]
    if repo_name.endswith('.git'):
        repo_name = repo_name[:-4]
    if ref_type == 'git_tag':
        ref_type = 'tag'
    elif ref_type == 'git_branch':
        ref_type = 'branch'
    # TODO: use config hostname, instead of https://git.almalinux.org
    return (
        f'https://git.almalinux.org/modules/{repo_name}'
        f'/raw/{ref_type}/{ref}/SOURCES/modulemd.src.txt'
    )


async def download_modules_yaml(url: str, ref: str, ref_type: str) -> str:
    template_path = modules_yaml_path_from_url(url, ref, ref_type)
    async with aiohttp.ClientSession() as session:
        async with session.get(template_path) as response:
            template = await response.text()
            try:
                response.raise_for_status()
            except aiohttp.ClientResponseError as error:
                if error.status == 404:
                    raise ModulesYamlNotFoundError()
                raise
            return template


class GiteaClient:
    def __init__(self, host: str, log: logging.Logger):
        self.host = host
        self.log = log
        self.requests_lock = asyncio.Semaphore(5)

    async def make_request(self, endpoint: str, params: dict = None):
        full_url = urllib.parse.urljoin(self.host, endpoint)

        max_retries = 5
        for attempt in range(1, max_retries + 1):
            try:
                self.log.debug(
                    f'Attempt to request [#{attempt}/{max_retries}]'
                    f' {full_url}, with params: {params}'
                )
                async with self.requests_lock:
                    async with aiohttp.ClientSession() as session:
                        async with session.get(
                            full_url, params=params
                        ) as response:
                            response.raise_for_status()
                            return await response.json()
            except (
                aiohttp.client_exceptions.ClientConnectorError,
                aiohttp.client_exceptions.ServerDisconnectedError,
            ) as e:
                wait = attempt * 2
                self.log.error(
                    f'Error during making request: {e}, {full_url}, {params}'
                )
                self.log.debug(
                    f'Retrying attempt [#{attempt}/{max_retries}] in'
                    f' {wait} seconds: {full_url}, with params: {params}'
                )
                await asyncio.sleep(wait)
                continue

    async def _list_all_pages(self, endpoint: str) -> typing.List:
        items = []
        page = 1
        # This is max gitea limit, default is 30
        items_per_page = 50
        while True:
            payload = {'limit': items_per_page, 'page': page}
            response = await self.make_request(endpoint, payload)
            items.extend(response)
            if len(response) < items_per_page:
                break
            page += 1
        return items

    async def list_repos(self, organization: str) -> typing.List:
        endpoint = f'orgs/{organization}/repos'
        return await self._list_all_pages(endpoint)

    async def list_tags(self, repo: str) -> typing.List:
        endpoint = f'repos/{repo}/tags'
        return await self._list_all_pages(endpoint)

    async def list_branches(self, repo: str) -> typing.List:
        endpoint = f'repos/{repo}/branches'
        return await self._list_all_pages(endpoint)

    async def get_branch(self, repo: str, branch: str) -> typing.Dict:
        endpoint = f'repos/{repo}/branches/{branch}'
        return await self.make_request(endpoint)

    async def index_repo(self, repo_name: str):
        tags = await self.list_tags(repo_name)
        branches = await self.list_branches(repo_name)
        return {'repo_name': repo_name, 'tags': tags, 'branches': branches}

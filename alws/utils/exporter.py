import os
import typing
import aiohttp
import aiofiles
import urllib
from pathlib import Path

from lxml.html import document_fromstring

from alws import database
from alws.crud import repo_exporter


async def fs_export_repository(repository_ids: list,
                               db: database.Session):
    export_task = await repo_exporter.create_pulp_exporters_to_fs(
        db, repository_ids)
    export_data = await repo_exporter.execute_pulp_exporters_to_fs(
        db, export_task)
    export_paths = list(export_data.keys())
    for repo_elem, repo_data in export_data.items():
        repo_url = urllib.parse.urljoin(repo_data, 'repodata/')
        res = await get_urls_from_html(repo_url)
        for url in res:
            dir_rd = Path(repo_elem).parent / 'repodata'
            os.makedirs(dir_rd, exist_ok=True)
            await download_file(url, dir_rd / Path(url).name)
    return export_paths


async def get_urls_from_html(base_url: str):
    async with aiohttp.ClientSession() as session:
        async with session.get(base_url) as response:
            response.raise_for_status()
            content = await response.text()
            doc = document_fromstring(content)
            children_urls = [base_url + a.get('href')
                             for a in doc.xpath('//a')]
            return children_urls


async def download_file(url: str, dest: str):
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as response:
            content = await response.content.read()
        async with aiofiles.open(dest, 'wb') as f:
            await f.write(content)

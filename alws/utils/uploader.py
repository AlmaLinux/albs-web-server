import io
import re
import urllib.parse

from alws.config import settings
from alws.utils.modularity import (
    IndexWrapper,
    get_random_unique_version,
)
from alws.utils.pulp_client import PulpClient


class MetadataUploader:
    def __init__(self):
        self.pulp = PulpClient(settings.pulp_host, settings.pulp_user,
                               settings.pulp_password)

    async def iter_repo(self, repo_href: str):
        next_page = repo_href
        while True:
            if 'limit' in next_page and re.search(
                    r'limit=(\d+)', next_page).groups()[0] == '100':
                next_page = next_page.replace('limit=100', 'limit=1000')
            parsed_url = urllib.parse.urlsplit(next_page)
            path = parsed_url.path + '?' + parsed_url.query
            page = await self.pulp.get_by_href(path)
            for pkg in page['results']:
                yield pkg
            next_page = page.get('next')
            if not next_page:
                break

    async def upload_comps(self, repo_href, comps_content):
        latest_repo_href = await self.pulp.get_repo_latest_version(repo_href)
        latest_repo_data = await self.pulp.get_latest_repo_present_content(
            latest_repo_href)
        comps_content_keys = (
            'rpm.packagecategory',
            'rpm.packagegroup',
            'rpm.packageenvironment',
            'rpm.packagelangpacks',
        )
        repo_data_hrefs = [
            latest_repo_data.get(key, {}).get('href')
            for key in comps_content_keys
        ]
        content_to_remove = []
        for repo_type_href in repo_data_hrefs:
            if repo_type_href is None:
                continue
            content_to_remove.extend([
                content['pulp_href']
                async for content in self.iter_repo(repo_type_href)
            ])
        data = {
            'file': io.StringIO(comps_content),
            'repository': repo_href,
        }
        created_resources = await self.pulp.upload_comps(data)
        if created_resources:
            await self.pulp.modify_repository(
                repo_href,
                add=created_resources,
                remove=content_to_remove,
            )

    async def upload_modules(self, repo_href, module_content):
        latest_repo_href = await self.pulp.get_repo_latest_version(repo_href)
        latest_repo_data = await self.pulp.get_latest_repo_present_content(
            latest_repo_href)
        repo_data_href = latest_repo_data.get('rpm.modulemd', {}).get('href')
        repo_modules_to_remove = []
        modules_to_add = []
        if repo_data_href is not None:
            repo_modules_to_remove = [
                module['pulp_href']
                async for module in self.iter_repo(repo_data_href)
            ]
        artifact_href, _ = await self.pulp.upload_file(module_content)
        _index = IndexWrapper.from_template(module_content)
        for module in _index.iter_modules():
            payload = {
                'relative_path': 'modules.yaml',
                'artifact': artifact_href,
                'name': module.name,
                'stream': module.stream,
                'version': get_random_unique_version(),
                'context': module.context,
                'arch': module.arch,
                'artifacts': [],
                'dependencies': [],
            }
            module_href = await self.pulp.create_module_by_payload(payload)
            modules_to_add.append(module_href)
        payload = {
            'remove_content_units': repo_modules_to_remove,
            'add_content_units': modules_to_add,
        }
        await self.pulp.modify_repository(repo_href, add=modules_to_add,
                                          remove=repo_modules_to_remove)
        return modules_to_add, repo_modules_to_remove

    async def process_uploaded_files(
        self,
        repo_name: str,
        module_content=None,
        comps_content=None,
    ):
        repo = await self.pulp.get_rpm_repository_by_params({
            'name__contains': repo_name})
        repo_href = repo['pulp_href']
        if module_content is not None:
            module_content = await module_content.read()
            await self.upload_modules(repo_href, module_content.decode())
        if comps_content is not None:
            comps_content = await comps_content.read()
            await self.upload_comps(repo_href, comps_content.decode())
        await self.pulp.create_rpm_publication(repo_href)

import io
import logging
import re
import typing
import urllib.parse

from alws.config import settings
from alws.utils.ids import get_random_unique_version
from alws.utils.modularity import IndexWrapper
from alws.utils.pulp_client import PulpClient


class MetadataUploader:
    def __init__(self):
        self.pulp = PulpClient(settings.pulp_host, settings.pulp_user,
                               settings.pulp_password)

    async def iter_repo(self, repo_href: str) -> dict:
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

    async def upload_comps(self, repo_href: str, comps_content: str) -> None:
        data = {
            'file': io.StringIO(comps_content),
            'repository': repo_href,
            'replace': 'true',
        }
        await self.pulp.upload_comps(data)
        await self.pulp.create_rpm_publication(repo_href)

    async def upload_modules(self, repo_href: str,
                             module_content: str) -> None:
        latest_repo_href = await self.pulp.get_repo_latest_version(repo_href)
        latest_repo_data = await self.pulp.get_latest_repo_present_content(
            latest_repo_href)
        module_content_keys = ('rpm.modulemd_defaults', 'rpm.modulemd')
        repo_data_hrefs = [
            latest_repo_data.get(key, {}).get('href')
            for key in module_content_keys
        ]
        modules_to_remove = []
        hrefs_to_add = []
        for repo_type_href in repo_data_hrefs:
            if repo_type_href is None:
                continue
            async for content in self.iter_repo(repo_type_href):
                # when we deleting modulemd's, associated packages also removes
                # from repository, we need to add them in next repo version
                modules_to_remove.append(content['pulp_href'])
                hrefs_to_add.extend(content.get('packages', []))
        artifact_href, _ = await self.pulp.upload_file(module_content)
        _index = IndexWrapper.from_template(module_content)
        module = next(_index.iter_modules())
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
        hrefs_to_add.append(await self.pulp.create_module_by_payload(payload))
        # we can't associate same packages in modules twice in one repo version
        # need to remove them before creating new modulemd
        await self.pulp.modify_repository(repo_href, remove=modules_to_remove)
        await self.pulp.create_rpm_publication(repo_href)
        # if we fall during next modifying repository, we can delete this
        # repo version and rollback all changes that makes upload
        new_version_href = await self.pulp.get_repo_latest_version(repo_href)
        try:
            await self.pulp.modify_repository(repo_href, add=hrefs_to_add)
            await self.pulp.create_rpm_publication(repo_href)
        except Exception:
            await self.pulp.delete_by_href(new_version_href,
                                           wait_for_result=True)
            logging.exception('Cannot restore packages in repo:')
            raise

    async def process_uploaded_files(
        self,
        repo_name: str,
        module_content: bytes = None,
        comps_content: bytes = None,
    ) -> typing.List[str]:
        repo = await self.pulp.get_rpm_repository_by_params({
            'name__contains': repo_name})
        repo_href = repo['pulp_href']
        updated_metadata = []
        if module_content is not None:
            module_content = await module_content.read()
            await self.upload_modules(repo_href, module_content.decode())
            updated_metadata.append('modules.yaml')
        if comps_content is not None:
            comps_content = await comps_content.read()
            await self.upload_comps(repo_href, comps_content.decode())
            updated_metadata.append('comps.xml')
        return updated_metadata

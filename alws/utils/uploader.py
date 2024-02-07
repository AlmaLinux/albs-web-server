import io
import logging
import re
import typing
import urllib.parse

from aiohttp.client_exceptions import ClientResponseError
from fastapi import UploadFile, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from alws import models
from alws.config import settings
from alws.errors import UploadError
from alws.utils.ids import get_random_unique_version
from alws.utils.modularity import IndexWrapper
from alws.utils.pulp_client import PulpClient


class MetadataUploader:
    def __init__(self, session: AsyncSession, repo_name: str):
        self.pulp = PulpClient(
            settings.pulp_host, settings.pulp_user, settings.pulp_password
        )
        self.session = session
        self.repo_name = repo_name

    async def iter_repo(self, repo_href: str) -> typing.AsyncIterator[dict]:
        next_page = repo_href
        while True:
            if (
                "limit" in next_page
                and re.search(r"limit=(\d+)", next_page).groups()[0] == "100"
            ):
                next_page = next_page.replace("limit=100", "limit=1000")
            parsed_url = urllib.parse.urlsplit(next_page)
            path = parsed_url.path + "?" + parsed_url.query
            page = await self.pulp.get_by_href(path)
            for pkg in page["results"]:
                yield pkg
            next_page = page.get("next")
            if not next_page:
                break

    async def upload_comps(self, repo_href: str, comps_content: str) -> None:
        data = {
            "file": io.StringIO(comps_content),
            "repository": repo_href,
            "replace": "true",
        }
        await self.pulp.upload_comps(data)
        await self.pulp.create_rpm_publication(repo_href)

    async def upload_modules(
        self,
        repo_href: str,
        module_content: str,
    ) -> None:
        latest_repo_href = await self.pulp.get_repo_latest_version(repo_href)
        if not latest_repo_href:
            raise ValueError(f"Cannot get latest repo version by {repo_href=}")
        latest_repo_data = await self.pulp.get_latest_repo_present_content(
            latest_repo_href
        )
        module_content_keys = ("rpm.modulemd_defaults", "rpm.modulemd")
        repo_data_hrefs = [
            latest_repo_data.get(key, {}).get("href")
            for key in module_content_keys
        ]
        modules_to_remove = []
        hrefs_to_add = []
        for repo_type_href in repo_data_hrefs:
            if repo_type_href is None:
                continue
            async for content in self.iter_repo(repo_type_href):
                modules_to_remove.append(content["pulp_href"])
        artifact_href, sha256 = await self.pulp.upload_file(module_content)
        _index = IndexWrapper.from_template(module_content)
        module = next(_index.iter_modules())
        payload = {
            "relative_path": "modules.yaml",
            "artifact": artifact_href,
            "name": module.name,
            "stream": module.stream,
            "version": get_random_unique_version(),
            "context": module.context,
            "arch": module.arch,
            "artifacts": [],
            "dependencies": [],
        }
        module_href = await self.pulp.create_module_by_payload(payload)
        hrefs_to_add.append(module_href)

        # we can't associate same packages in modules twice in one repo version
        # need to remove them before creating new modulemd
        task_result = await self.pulp.modify_repository(
            repo_href,
            remove=modules_to_remove,
        )
        logging.debug(
            'Removed the following entities from repo "%s":\n%s',
            repo_href,
            modules_to_remove,
        )
        # if we fall during next modifying repository, we can delete this
        # repo version and rollback all changes that makes upload
        new_version_href = next(
            (
                resource
                for resource in task_result.get("created_resources", [])
                if re.search(rf"{repo_href}versions/\d+/$", resource)
            ),
            None,
        )
        # not sure, but keep it for failsafe if we doesn't have new created
        # repo version from modify task result
        if not new_version_href:
            new_version_href = await self.pulp.get_repo_latest_version(
                repo_href,
            )

        # when we deleting modulemd's, associated packages also removes
        # from repository, we need to add them in next repo version
        removed_content = await self.pulp.get_latest_repo_removed_content(
            new_version_href
        )
        removed_pkgs_href = removed_content.get("rpm.package", {}).get("href")
        # in case if early removed modules doesn't contains associated packages
        if removed_pkgs_href:
            async for pkg in self.iter_repo(removed_pkgs_href):
                hrefs_to_add.append(pkg["pulp_href"])

        try:
            logging.debug(
                'Trying to add early removed packages in the repo "%s":\n%s',
                repo_href,
                hrefs_to_add,
            )
            await self.pulp.modify_repository(repo_href, add=hrefs_to_add)
        except Exception as exc:
            await self.pulp.delete_by_href(
                new_version_href,
                wait_for_result=True,
            )
            logging.exception("Cannot restore packages in repo:")
            raise exc
        finally:
            await self.pulp.create_rpm_publication(repo_href)

        # we need to update module if we update template in build repo
        re_result = re.search(
            # AlmaLinux-8-s390x-0000-debug-br
            r".+-(?P<arch>\w+)-(?P<build_id>\d+)(-br|-debug-br)$",
            self.repo_name,
            flags=re.IGNORECASE,
        )
        if not re_result:
            return
        re_result = re_result.groupdict()
        subq = (
            select(models.BuildTask.rpm_module_id)
            .where(
                models.BuildTask.build_id == int(re_result["build_id"]),
                models.BuildTask.arch == re_result["arch"],
            )
            .scalar_subquery()
        )
        rpm_modules = (
            (
                await self.session.execute(
                    select(models.RpmModule).where(
                        models.RpmModule.id.in_(subq),
                    )
                )
            )
            .scalars()
            .all()
        )
        for rpm_module in rpm_modules:
            for attr in (
                "name",
                "version",
                "stream",
                "context",
                "arch",
            ):
                module_value = str(getattr(module, attr))
                if module_value != str(getattr(rpm_module, attr)):
                    setattr(rpm_module, attr, module_value)
            rpm_module.pulp_href = module_href
        await self.session.commit()

    async def process_uploaded_files(
        self,
        module_content: typing.Optional[UploadFile] = None,
        comps_content: typing.Optional[UploadFile] = None,
    ) -> typing.List[str]:
        repo = await self.pulp.get_rpm_repository_by_params(
            {"name": self.repo_name},
        )
        if not repo:
            raise UploadError(
                f"{repo=} not found",
                status=status.HTTP_404_NOT_FOUND,
            )
        logging.debug("Start processing upload for repo: %s", repo["name"])
        repo_href = repo["pulp_href"]
        updated_metadata = []
        try:
            if module_content is not None:
                module_content = await module_content.read()
                await self.upload_modules(repo_href, module_content.decode())
                updated_metadata.append("modules.yaml")
            if comps_content is not None:
                comps_content = await comps_content.read()
                await self.upload_comps(repo_href, comps_content.decode())
                updated_metadata.append("comps.xml")
        except ClientResponseError as exc:
            raise UploadError(exc.message, exc.status)
        except Exception as exc:
            raise UploadError(str(exc))
        return updated_metadata

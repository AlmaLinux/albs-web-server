import datetime
import hashlib
import io
import logging
import re
import typing
import urllib.parse

from aiohttp.client_exceptions import ClientResponseError
from fastapi import UploadFile, status
from sqlalchemy import (
    and_,
    or_,
    select,
    update,
)
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from alws import models
from alws.config import settings
from alws.dependencies import get_pulp_db
from alws.errors import UploadError
from alws.pulp_models import CoreContent, RpmModulemd, RpmModulemdDefaults
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

    async def upload_comps(
        self,
        repo_href: str,
        comps_content: str,
        dry_run: bool = False,
    ) -> None:
        if dry_run:
            logging.info("DRY_RUN: Uploading comps:\n%s", comps_content)
            return
        logging.info("Uploading comps file")
        data = {
            "file": io.StringIO(comps_content),
            "repository": repo_href,
            "replace": "true",
        }
        await self.pulp.upload_comps(data)
        await self.pulp.create_rpm_publication(repo_href)
        logging.info("Comps file upload has been finished")

    async def upload_modules(
        self,
        repo_href: str,
        module_content: str,
        dry_run: bool = False,
    ):
        db_modules = []
        module_hrefs = []
        defaults_hrefs = []
        _index = IndexWrapper.from_template(module_content)
        with get_pulp_db() as pulp_session:
            for module in _index.iter_modules():
                defaults_snippet = _index.get_module_defaults_as_str(module.name)
                defaults_checksum = hashlib.sha256(
                    defaults_snippet.encode('utf-8')
                ).hexdigest()
                pulp_module = (
                    pulp_session.execute(
                        select(RpmModulemd).where(
                            RpmModulemd.name == module.name,
                            RpmModulemd.arch == module.arch,
                            RpmModulemd.stream == module.stream,
                            RpmModulemd.version == str(module.version),
                            RpmModulemd.context == module.context,
                        )
                    )
                    .scalars()
                    .first()
                )
                pulp_defaults = (
                    pulp_session.execute(
                        select(RpmModulemdDefaults).where(
                            and_(
                                RpmModulemdDefaults.module == module.name,
                                or_(
                                    RpmModulemdDefaults.digest == None,
                                    RpmModulemdDefaults.digest == defaults_checksum,
                                )
                            )
                        )
                    )
                    .scalars()
                    .first()
                )
                module_snippet = module.render()
                if not pulp_module:
                    if dry_run:
                        logging.info(
                            "DRY_RUN: Module is not present in Pulp, creating"
                        )
                        continue
                    logging.info("Module is not present in Pulp, creating")
                    pulp_href = await self.pulp.create_module(
                        module_snippet,
                        module.name,
                        module.stream,
                        module.context,
                        module.arch,
                        module.description,
                        version=module.version,
                        artifacts=module.get_rpm_artifacts(),
                        dependencies=list(module.get_runtime_deps().values()),
                        packages=[],
                        profiles=module.get_profiles(),
                    )
                    db_module = models.RpmModule(
                        name=module.name,
                        stream=module.stream,
                        context=module.context,
                        arch=module.arch,
                        version=str(module.version),
                        pulp_href=pulp_href,
                    )
                    db_modules.append(db_module)
                else:
                    if dry_run:
                        logging.info(
                            "DRY_RUN: Updating existing module in Pulp"
                        )
                        continue
                    logging.info("Updating existing module in Pulp")
                    pulp_session.execute(
                        update(RpmModulemd)
                        .where(
                            RpmModulemd.content_ptr_id
                            == pulp_module.content_ptr_id
                        )
                        .values(
                            snippet=module_snippet,
                            description=module.description,
                        )
                    )
                    pulp_session.execute(
                        update(CoreContent)
                        .where(
                            CoreContent.pulp_id == pulp_module.content_ptr_id
                        )
                        .values(pulp_last_updated=datetime.datetime.now())
                    )
                    pulp_href = (f'/pulp/api/v3/content/rpm/modulemds/'
                                 f'{pulp_module.content_ptr_id}/')
                module_hrefs.append(pulp_href)

                default_profiles = _index.get_module_default_profiles(
                    module.name, module.stream
                )
                href = None
                if not pulp_defaults and defaults_snippet and default_profiles:
                    href = await self.pulp.create_module_defaults(
                        module.name,
                        module.stream,
                        default_profiles,
                        defaults_snippet
                    )
                elif pulp_defaults and defaults_snippet and default_profiles:
                    pulp_session.execute(
                        update(RpmModulemdDefaults)
                        .where(
                            RpmModulemdDefaults.content_ptr_id
                            == pulp_defaults.content_ptr_id
                        )
                        .values(
                            profiles=default_profiles,
                            snippet=defaults_snippet
                        )
                    )
                    pulp_session.execute(
                        update(CoreContent)
                        .where(
                            CoreContent.pulp_id == pulp_defaults.content_ptr_id
                        )
                        .values(pulp_last_updated=datetime.datetime.now())
                    )
                    href = (f'/pulp/api/v3/content/rpm/modulemd_defaults/'
                            f'{pulp_defaults.content_ptr_id}/')
                if href:
                    defaults_hrefs.append(href)
            pulp_session.commit()
        if db_modules and not dry_run:
            self.session.add_all(db_modules)
            await self.session.commit()
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
            build_tasks = (
                (
                    await self.session.execute(
                        select(models.BuildTask)
                        .where(
                            models.BuildTask.build_id
                            == int(re_result["build_id"]),
                            models.BuildTask.arch == re_result["arch"],
                        )
                        .options(selectinload(models.BuildTask.rpm_modules))
                    )
                )
                .scalars()
                .all()
            )
            for task in build_tasks:
                task.rpm_modules = db_modules
                self.session.add(task)
            await self.session.commit()

        if module_hrefs and not dry_run:
            logging.info("Getting information about repository")
            modules_in_version = await self.pulp.get_repo_modules(repo_href)
            logging.info("Deleting previous listed modules")
            await self.pulp.modify_repository(
                repo_href, remove=modules_in_version
            )
            logging.info("Adding created modules to repository")
            await self.pulp.modify_repository(repo_href, add=module_hrefs)
        if defaults_hrefs and not dry_run:
            logging.info("Adding created modules defaults to repository")
            await self.pulp.modify_repository(repo_href, add=defaults_hrefs)
        if not dry_run:
            logging.info("Publishing new repository version")
            await self.pulp.create_rpm_publication(repo_href)
        logging.info("Modules upload has been finished")

    async def process_uploaded_files(
        self,
        module_content: typing.Optional[UploadFile] = None,
        comps_content: typing.Optional[UploadFile] = None,
        dry_run: bool = False,
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
                await self.upload_modules(
                    repo_href,
                    module_content.decode(),
                    dry_run=dry_run,
                )
                updated_metadata.append("modules.yaml")
            if comps_content is not None:
                comps_content = await comps_content.read()
                await self.upload_comps(
                    repo_href,
                    comps_content.decode(),
                    dry_run=dry_run,
                )
                updated_metadata.append("comps.xml")
        except ClientResponseError as exc:
            raise UploadError(exc.message, exc.status)
        except Exception as exc:
            raise UploadError(str(exc))
        return updated_metadata

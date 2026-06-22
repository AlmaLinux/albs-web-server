import datetime
import hashlib
import io
import logging
import re
import typing

from aiohttp.client_exceptions import ClientResponseError
from fastapi import UploadFile, status
from fastapi_sqla import open_session
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from alws import models
from alws.config import settings
from alws.errors import UploadError
from alws.pulp_models import CoreContent, RpmModulemd, RpmModulemdDefaults
from alws.utils.modularity import IndexWrapper
from alws.utils.pulp_client import PulpClient
from alws.utils.pulp_utils import (
    get_removed_rpm_packages_from_latest_repo_version,
    get_uuid_from_pulp_href,
)


class MetadataUploader:
    def __init__(self, session: AsyncSession, repo_name: str):
        self.pulp = PulpClient(
            settings.pulp_host,
            settings.pulp_user,
            settings.pulp_password,
        )
        self.session = session
        self.repo_name = repo_name

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

    async def upload_rpm_modules(
        self,
        module_content: str,
        dry_run: bool = False,
    ):
        db_modules = []
        module_hrefs = []
        defaults_hrefs = []
        _index = IndexWrapper.from_template(module_content)
        with open_session('pulp') as pulp_session:
            for module in _index.iter_modules():
                defaults_snippet = _index.get_module_defaults_as_str(module.name)
                defaults_checksum = hashlib.sha256(defaults_snippet.encode('utf-8')).hexdigest()
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
                conditions = [
                    (
                        RpmModulemdDefaults.module == module.name,
                        RpmModulemdDefaults.digest == defaults_checksum,
                    ),
                    (
                        RpmModulemdDefaults.module == module.name,
                        RpmModulemdDefaults.stream == module.stream,
                    ),
                    (RpmModulemdDefaults.module == module.name,),
                ]
                pulp_defaults = None
                for cond in conditions:
                    pulp_defaults = (
                        pulp_session.execute(select(RpmModulemdDefaults).where(*cond))
                        .scalars()
                        .first()
                    )
                    if pulp_defaults:
                        break
                module_snippet = module.render()
                if not pulp_module:
                    if dry_run:
                        logging.info("DRY_RUN: Module is not present in Pulp, creating")
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
                        logging.info("DRY_RUN: Updating existing module in Pulp")
                        continue
                    logging.info("Updating existing module in Pulp")
                    pulp_session.execute(
                        update(RpmModulemd)
                        .where(RpmModulemd.content_ptr_id == pulp_module.content_ptr_id)
                        .values(
                            snippet=module_snippet,
                            description=module.description,
                        )
                    )
                    pulp_session.execute(
                        update(CoreContent)
                        .where(CoreContent.pulp_id == pulp_module.content_ptr_id)
                        .values(pulp_last_updated=datetime.datetime.now())
                    )
                    pulp_href = f'/pulp/api/v3/content/rpm/modulemds/{pulp_module.content_ptr_id}/'
                module_hrefs.append(pulp_href)

                href = None
                default_profiles = _index.get_module_default_profiles(module.name, module.stream)
                if not pulp_defaults and defaults_snippet and default_profiles:
                    href = await self.pulp.create_module_defaults(
                        module.name,
                        module.stream,
                        default_profiles,
                        defaults_snippet,
                    )
                elif pulp_defaults and defaults_snippet and default_profiles:
                    pulp_session.execute(
                        update(RpmModulemdDefaults)
                        .where(RpmModulemdDefaults.content_ptr_id == pulp_defaults.content_ptr_id)
                        .values(
                            profiles=default_profiles,
                            snippet=defaults_snippet,
                            digest=defaults_checksum,
                        )
                    )
                    pulp_session.execute(
                        update(CoreContent)
                        .where(CoreContent.pulp_id == pulp_defaults.content_ptr_id)
                        .values(pulp_last_updated=datetime.datetime.now())
                    )
                    href = (
                        f'/pulp/api/v3/content/rpm/modulemd_defaults/'
                        f'{pulp_defaults.content_ptr_id}/'
                    )
                if href:
                    defaults_hrefs.append(href)
        return db_modules, module_hrefs, defaults_hrefs

    async def upload_modules(
        self,
        repo_href: str,
        module_content: str,
        dry_run: bool = False,
    ):
        db_modules, module_hrefs, defaults_hrefs = await self.upload_rpm_modules(
            module_content,
            dry_run,
        )
        if db_modules and not dry_run:
            self.session.add_all(db_modules)
            await self.session.flush()
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
                            models.BuildTask.build_id == int(re_result["build_id"]),
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
            await self.session.flush()

        removed_pkgs = get_removed_rpm_packages_from_latest_repo_version(
            get_uuid_from_pulp_href(repo_href),
        )
        final_additions = module_hrefs.copy()
        if defaults_hrefs:
            final_additions.extend(defaults_hrefs)
        if final_additions and not dry_run:
            logging.info("Getting information about repository")
            modules_in_version = await self.pulp.get_repo_modules(repo_href)
            logging.info("Adding modules and defaults to repository")
            await self.pulp.modify_repository(
                repo_href,
                add=final_additions,
                remove=modules_in_version,
            )
        if removed_pkgs:
            logging.info('Adding removed packages to repository')
            await self.pulp.modify_repository(
                repo_href,
                add=[pkg.pulp_href for pkg in removed_pkgs],
            )
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

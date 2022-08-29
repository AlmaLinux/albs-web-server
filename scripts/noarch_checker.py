import argparse
import asyncio
from contextlib import asynccontextmanager
import datetime
import logging
import os
import sys
import typing
import urllib.parse

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Query, selectinload

sys.path.append(os.path.dirname(os.path.dirname(__file__)))

from alws.models import Platform, Product, Repository
from alws.config import settings
from alws.dependencies import get_db
from alws.utils import pulp_client


class NoarchProcessor:
    def __init__(
        self,
        session: AsyncSession,
        source_obj_name: str,
        source_type: str,
        dest_obj_name: str,
        dest_type: str,
        only_check: bool = False,
        show_diff: bool = False,
        only_copy: bool = False,
        only_replace: bool = False,
    ):
        current_ts = int(datetime.datetime.now().timestamp())
        logging.basicConfig(
            format='%(asctime)s %(levelname)-8s %(message)s',
            level=logging.INFO,
            datefmt='%Y-%m-%d %H:%M:%S',
            handlers=[
                logging.StreamHandler(),
                logging.FileHandler(f'noarch_processor.{current_ts}.log'),
            ],
        )
        self.logger = logging.getLogger('noarch-processor')
        self.pulp = pulp_client.PulpClient(
            settings.pulp_host,
            settings.pulp_user,
            settings.pulp_password,
        )
        self.session = session
        self.source_obj_name = source_obj_name
        self.source_type = source_type
        self.dest_obj_name = dest_obj_name
        self.dest_type = dest_type
        self.only_check = only_check
        self.show_diff = show_diff
        self.only_copy = only_copy
        self.only_replace = only_replace

    @staticmethod
    def get_full_repo_name(repo: Repository) -> str:
        return f"{repo.name}-{'debuginfo-' if repo.debug else ''}{repo.arch}"

    async def retrieve_all_packages_from_repo(
        self,
        latest_repo_version: str,
    ) -> typing.List[typing.Dict[str, str]]:
        endpoint = "pulp/api/v3/content/rpm/packages/"
        params = {
            "arch": "noarch",
            "fields": ",".join((
                "name",
                "version",
                "release",
                "sha256",
                "pulp_href",
            )),
            "repository_version": latest_repo_version,
        }
        response = await self.pulp.request("GET", endpoint, params=params)
        packages = response["results"]
        while response.get("next"):
            new_url = response.get("next")
            parsed_url = urllib.parse.urlsplit(new_url)
            new_url = parsed_url.path + "?" + parsed_url.query
            response = await self.pulp.request("GET", new_url)
            packages.extend(response["results"])
        return packages

    async def copy_noarch_packages_from_source(
        self,
        source_repo_name: str,
        source_repo_packages: typing.List[dict],
        destination_repo_name: str,
        destination_repo_href: str,
    ) -> None:
        self.logger.info(
            'Collecting packages from: "%s"', destination_repo_name,
        )
        destination_repo_packages = await self.retrieve_all_packages_from_repo(
            await self.pulp.get_repo_latest_version(destination_repo_href)
        )

        packages_to_add = []
        packages_to_remove = []
        add_msg = 'Package "%s" added from "%s" repo into "%s" repo'
        replace_msg = 'Package "%s" replaced in "%s" repo from "%s" repo'
        if self.only_check:
            add_msg = 'Package "%s" can be added from "%s" repo into "%s" repo'
            replace_msg = 'Package "%s" can be replaced in "%s" repo from "%s" repo'
        for package_dict in source_repo_packages:
            pkg_name = package_dict["name"]
            pkg_version = package_dict["version"]
            pkg_release = package_dict["release"]
            is_modular = ".module_el" in pkg_release
            full_name = f"{pkg_name}-{pkg_version}-{pkg_release}.noarch.rpm"
            compared_pkg = next((
                pkg for pkg in destination_repo_packages
                if all((
                    pkg["name"] == pkg_name,
                    pkg["version"] == pkg_version,
                    pkg["release"] == pkg_release,
                ))
            ), None)
            if compared_pkg is None and not self.only_replace:
                if is_modular or self.show_diff:
                    continue
                packages_to_add.append(package_dict["pulp_href"])
                self.logger.info(
                    add_msg, full_name, source_repo_name, destination_repo_name
                )
                continue
            if (
                package_dict["sha256"] != compared_pkg["sha256"]
                and not self.only_copy
            ):
                if not self.show_diff:
                    packages_to_remove.append(compared_pkg["pulp_href"])
                    packages_to_add.append(package_dict["pulp_href"])
                self.logger.info(
                    replace_msg, full_name,
                    destination_repo_name, source_repo_name
                )

        if packages_to_add and not self.only_check:
            await self.pulp.modify_repository(
                destination_repo_href,
                add=packages_to_add,
                remove=packages_to_remove,
            )
            await self.pulp.create_rpm_publication(
                destination_repo_href,
            )

    async def prepare_and_execute_async_tasks(
        self,
        source_repo_dict: dict,
        dest_repo_dict: dict,
    ) -> None:
        tasks = []
        for source_repo_name, repo_data in source_repo_dict.items():
            repo_href, source_is_debug = repo_data
            self.logger.info(
                'Collecting packages from: "%s"', source_repo_name,
            )
            source_repo_packages = await self.retrieve_all_packages_from_repo(
                await self.pulp.get_repo_latest_version(repo_href),
            )
            for dest_repo_name, dest_repo_data in dest_repo_dict.items():
                dest_repo_href, dest_repo_is_debug = dest_repo_data
                if source_is_debug != dest_repo_is_debug:
                    continue
                tasks.append(self.copy_noarch_packages_from_source(
                    source_repo_name=source_repo_name,
                    source_repo_packages=source_repo_packages,
                    destination_repo_name=dest_repo_name,
                    destination_repo_href=dest_repo_href,
                ))
        self.logger.info('Start checking noarch packages in repos')
        await asyncio.gather(*tasks)
        self.logger.info('Checking noarch packages in repos is done')

    def get_model_query(self, is_dest=False) -> Query:
        model_type = self.dest_type if is_dest else self.source_type
        obj_name = self.dest_obj_name if is_dest else self.source_obj_name
        if model_type not in ("platform", "product", "repository"):
            raise ValueError(f"Wrong model type: {model_type}")
        if model_type == "platform":
            model = Platform
            conditions = (
                Platform.name == obj_name,
            )
            options = (
                selectinload(Platform.repos),
            )
        if model_type == "product":
            model = Product
            conditions = (
                Product.name == obj_name,
            )
            options = (
                selectinload(Product.repositories),
            )
        return select(model).where(*conditions).options(*options)

    @staticmethod
    def get_repos_collection(
        obj: typing.Union[Platform, Product],
    ) -> typing.List[Repository]:
        if isinstance(obj, Platform):
            repos_collection = obj.repos
        elif isinstance(obj, Product):
            repos_collection = obj.repositories
        return repos_collection

    async def run(self):
        source_query = self.get_model_query()
        dest_query = self.get_model_query(is_dest=True)
        src_obj = (await self.session.execute(source_query)).scalars().first()
        dest_obj = (await self.session.execute(dest_query)).scalars().first()
        if not src_obj:
            raise ValueError(
                f"Source obj: {self.source_obj_name} doesn't exist"
            )
        if not dest_obj:
            raise ValueError(
                f"Destination obj: {self.dest_obj_name} doesn't exist"
            )
        source_repos = {}
        dest_repos = {}
        for is_dest in (False, True):
            obj = src_obj
            repos_dict = source_repos
            if is_dest:
                obj = dest_obj
                repos_dict = dest_repos
            for repo in self.get_repos_collection(obj):
                repo_name = self.get_full_repo_name(repo)
                if repo.arch != 'x86_64' and not is_dest or repo.arch == 'src':
                    continue
                repos_dict[repo_name] = (repo.pulp_href, repo.debug)
        await self.prepare_and_execute_async_tasks(source_repos, dest_repos)


def parse_args():
    parser = argparse.ArgumentParser(
        "noarch_checker",
        description="""
        Noarch packages checker script.
        Checks noarch packages in source and destination repos
        and copy/replace them"
        """,
    )
    parser.add_argument(
        "-s",
        "--source",
        type=str,
        required=True,
        help="Source platform/product name",
    )
    parser.add_argument(
        "--source-type",
        type=str,
        required=False,
        default="platform",
        help=(
            "Source object type (platform/product), "
            "default value is `platform`"
        ),
    )
    parser.add_argument(
        "-d",
        "--destination",
        type=str,
        required=True,
        help="Destination platform/product name",
    )
    parser.add_argument(
        "--dest-type",
        type=str,
        required=False,
        default="product",
        help=(
            "Destination object type (platform/product), "
            "default value is `product`",
        ),
    )
    parser.add_argument(
        "-D",
        "--show-diff",
        action="store_true",
        default=False,
        required=False,
        help="Shows/process only packages that have different checksum",
    )
    parser.add_argument(
        "-O",
        "--only-check",
        action="store_true",
        default=False,
        required=False,
        help="Only check noarch packages without copying",
    )
    parser.add_argument(
        "-C",
        "--only-copy",
        action="store_true",
        default=False,
        required=False,
        help="Copy noarch packages without replacing",
    )
    parser.add_argument(
        "-R",
        "--only-replace",
        action="store_true",
        default=False,
        required=False,
        help="Replace noarch packages without copying",
    )
    return parser.parse_args()


async def main():
    args = parse_args()
    pulp_client.PULP_SEMAPHORE = asyncio.Semaphore(10)
    async with asynccontextmanager(get_db)() as session:
        processor = NoarchProcessor(
            session=session,
            source_obj_name=args.source,
            source_type=args.source_type,
            dest_obj_name=args.destination,
            dest_type=args.dest_type,
            only_check=args.only_check,
            show_diff=args.show_diff,
            only_copy=args.only_copy,
            only_replace=args.only_replace,
        )
        await processor.run()


if __name__ == "__main__":
    asyncio.run(main())

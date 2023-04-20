import argparse
import asyncio
import datetime
import logging
import os
import pprint
import sys
import typing

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

sys.path.append(os.path.dirname(os.path.dirname(__file__)))

from alws.models import (
    Platform,
    PlatformFlavour,
    Product,
    Repository,
)
from alws.config import settings
from alws.database import Session
from alws.utils import pulp_client
from alws.utils.debuginfo import is_debuginfo


SUPPORTED_ARCHES = ("src", "aarch64", "i686", "ppc64le",
                    "s390x", "x86_64")
MODEL_MAPPING = {
    "flavor": PlatformFlavour,
    "platform": Platform,
    "product": Product,
}


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "-s", "--stable-platform", type=str, required=True,
        help="Stable platform name to compare beta with"
    )
    parser.add_argument(
        "-b", "--beta-entity", type=str, required=True,
        help="Beta entity name to compare stable with"
    )
    parser.add_argument(
        "--beta-type", choices=("flavor", "product"), type=str,
        default="flavor",
        help="Beta entity type to query for repositories"
    )
    parser.add_argument(
        "-a", "--arch",
        choices=SUPPORTED_ARCHES, type=str, default="",
        help="Check a specific architecture only"
    )
    parser.add_argument(
        "-v", "--verbose", action="store_true",
        help="Enable verbose output"
    )
    return parser.parse_args()


async def get_repositories(
        session: AsyncSession,
        entity_name: str,
        model_type: str = "platform",
        arch: typing.Optional[str] = None) -> typing.List[Repository]:

    model = MODEL_MAPPING[model_type]
    entity_class_name = model.__class__.__name__
    if hasattr(model, "repos"):
        repositories_field = model.repos
        field_name = "repos"
    elif hasattr(model, "repositories"):
        field_name = "repositories"
        repositories_field = model.repositories
    else:
        raise ValueError(
            f"Cannot get list of the repositories "
            f"from the provided entity: {entity_class_name}"
        )
    entity = (
        await session.execute(select(model).where(
            model.name == entity_name).options(
            selectinload(repositories_field)
        ))
    ).scalars().first()
    if not entity:
        raise ValueError(f"Cannot find {entity_class_name.lower()} "
                         f"with name {entity_name}")
    if arch:
        return [r for r in getattr(entity, field_name, [])]
    return list(getattr(entity, field_name, []))


class PackagesComparator:
    def __init__(self):
        self.pulp = pulp_client.PulpClient(
            settings.pulp_host, settings.pulp_user,
            settings.pulp_password
        )

    async def retrieve_all_packages_from_repo(
            self,
            repository: Repository,
            arch: typing.Optional[str] = None
    ) -> typing.Tuple[str, typing.List[typing.Dict[str, str]]]:

        logging.info("Getting packages from repository %s",
                     repository.name)
        search_params = {}
        if arch:
            if arch == "src":
                search_params["arch"] = arch
            else:
                search_params["arch__in"] = (arch, "noarch")
        packages = await self.pulp.get_rpm_repository_packages(
            repository.pulp_href,
            include_fields=["sha256", "location_href"],
            **search_params,
        )
        logging.info("Got all packages from repository %s",
                     repository.name)
        return repository.name, packages

    async def get_packages_list(
            self,
            repositories: typing.List[Repository],
            arch: typing.Optional[str] = None
    ) -> typing.Tuple[typing.Set[str], typing.Set[str]]:
        tasks = []
        for repository in repositories:
            if repository.pulp_href:
                tasks.append(
                    self.retrieve_all_packages_from_repo(
                        repository, arch=arch
                    )
                )
            else:
                logging.warning("Repository %s does not have Pulp HREF",
                                str(repository))

        packages = await asyncio.gather(*tasks)
        debuginfo_packages = []
        usual_packages = []

        logging.debug("All packages: %s", pprint.pformat(packages))

        for repo_name, packages in packages:
            package_names = [p["location_href"].split("/")[-1]
                             for p in packages]
            if is_debuginfo(repo_name):
                debuginfo_packages.extend(package_names)
            else:
                usual_packages.extend(package_names)

        return set(usual_packages), set(debuginfo_packages)

    async def run(self, args):
        async with Session() as session:
            stable_repositories = await get_repositories(
                session, args.stable_platform, arch=args.arch
            )
            beta_repositories = await get_repositories(
                session, args.beta_entity, model_type=args.beta_type,
                arch=args.arch
            )

        stable_usual_packages, stable_debuginfo_packages = (
            await self.get_packages_list(
                stable_repositories, arch=args.arch)
        )

        beta_usual_packages, beta_debuginfo_packages = (
            await self.get_packages_list(
                beta_repositories, arch=args.arch)
        )

        usual_diff = set(stable_usual_packages) & set(beta_usual_packages)
        debuginfo_diff = set(stable_debuginfo_packages) & set(beta_debuginfo_packages)
        if usual_diff:
            logging.error("Beta packages have intersections "
                          "with stable: %s", pprint.pformat(usual_diff))
        if debuginfo_diff:
            logging.error("Beta debuginfo packages have intersections "
                          "with stable: %s", pprint.pformat(debuginfo_diff))


async def main():
    args = parse_args()
    current_ts = int(datetime.datetime.utcnow().timestamp())
    logging.basicConfig(
        format="%(asctime)s %(levelname)-8s %(message)s",
        level=logging.DEBUG if args.verbose else logging.INFO,
        datefmt="%Y-%m-%d %H:%M:%S",
        handlers=[
            logging.StreamHandler(),
            logging.FileHandler(f"stable_beta_comparator.{current_ts}.log"),
        ],
    )
    comparator = PackagesComparator()
    await comparator.run(args)


if __name__ == "__main__":
    asyncio.get_event_loop().run_until_complete(main())

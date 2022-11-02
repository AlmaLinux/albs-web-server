import asyncio
from collections import namedtuple
import logging
import os
import re
import sys
import typing
import urllib.parse

import aiohttp
from sqlalchemy import select

sys.path.append(os.path.dirname(os.path.dirname(__file__)))

from alws.config import settings
from alws.database import SyncSession
from alws.models import Platform, Repository
from alws.utils import pulp_client
from alws.utils.modularity import IndexWrapper, ModuleWrapper


logging.basicConfig(
    format="%(asctime)s %(levelname)-8s %(message)s",
    level=logging.INFO,
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("albs_721.log"),
    ],
)
NSVCA = namedtuple("NSVCA", ("name", "version", "stream", "context", "arch"))


async def get_modules_from_repo_repodata(
    repodata_url: str,
) -> typing.Optional[str]:
    async with aiohttp.ClientSession() as session:
        async with session.get(repodata_url) as response:
            template_path = await response.text()
            result = None
            for line in template_path.splitlines():
                line = line.strip()
                match = re.search(
                    r"^.+>(.*modules.yaml)<.+$",
                    line,
                )
                if match:
                    result = match.group(1)
                    break
            if not result:
                return
            response.raise_for_status()
            return result


async def download_modules_from_repo(template_path: str) -> str:
    async with aiohttp.ClientSession() as session:
        async with session.get(template_path) as response:
            template = await response.text()
            response.raise_for_status()
            return template


def prepare_modules_cache(
    module_index: IndexWrapper,
) -> typing.Dict[NSVCA, ModuleWrapper]:
    cache = {}
    for module in module_index.iter_modules():
        key = NSVCA(
            module.name,
            module.stream,
            module.version,
            module.context,
            module.arch,
        )
        cache[key] = module
    return cache


async def list_errata_pulp(
    repo_href: str,
    pulp: pulp_client.PulpClient,
) -> typing.List[typing.Dict[str, typing.Any]]:
    endpoint = "pulp/api/v3/content/rpm/advisories/"
    params = {
        "fields": "id,pulp_href,pkglist",
        "repository_version": repo_href,
    }
    result = []

    response = await pulp.request("GET", endpoint, params=params)
    next_page = response.get("next")
    result.extend(response.get("results", []))
    if not next_page:
        return result
    while True:
        if (
            "limit" in next_page
            and re.search(r"limit=(\d+)", next_page).groups()[0] == "100"
        ):
            next_page = next_page.replace("limit=100", "limit=1000")
        parsed_url = urllib.parse.urlsplit(next_page)
        path = parsed_url.path + "?" + parsed_url.query
        response = await pulp.get_by_href(path)
        next_page = response.get("next")
        result.extend(response.get("results", []))
        if not next_page:
            break
    return result


async def get_module_index(repo: Repository, repo_name: str):
    repodata_url = urllib.parse.urljoin(repo.url, "repodata/")
    try:
        template_path = await get_modules_from_repo_repodata(repodata_url)
        if not template_path:
            return
        template = await download_modules_from_repo(
            urllib.parse.urljoin(repo.url, f"repodata/{template_path}")
        )
    except Exception:
        logging.exception(
            "Cannot download module template for %s",
            repo_name,
        )
        return
    return IndexWrapper.from_template(template)


def get_nevra(pkg: typing.Dict[str, typing.Any]) -> str:
    return (
        f"{pkg['name']}-{pkg['epoch']}:{pkg['version']}-{pkg['release']}.{pkg['arch']}"
    )


def get_module_artifacts(module: ModuleWrapper) -> typing.List[str]:
    return module._stream.get_rpm_artifacts()


def find_wrong_modules_in_record(
    errata: dict,
    repo_modules_cache: typing.Dict[NSVCA, ModuleWrapper],
):

    for collection in errata.get("pkglist", []):
        module = collection.get("module", {})
        if not module:
            continue
        module_cache_key = NSVCA(
            module["name"],
            module["stream"],
            module["version"],
            module["context"],
            module["arch"],
        )
        repo_module = repo_modules_cache.get(module_cache_key)
        if not repo_module:
            continue
        module_artifacts = get_module_artifacts(repo_module)
        wrong_pkgs = []
        for pkg in collection.get("packages", []):
            nevra = get_nevra(pkg)
            if nevra in module_artifacts:
                continue
            wrong_pkgs.append(nevra)
        if not wrong_pkgs:
            continue
        logging.info(
            "Record %s contains module packages that doesn`t belongs to module '%s': %s",
            errata["id"],
            ":".join(str(el) for el in module_cache_key),
            ", ".join(wrong_pkgs),
        )
        possible_module_keys = [
            key
            for key in repo_modules_cache
            if key.name == module["name"] and key.arch == module["arch"]
        ]
        for key in possible_module_keys:
            repo_module = repo_modules_cache[key]
            module_artifacts = get_module_artifacts(repo_module)
            belongs_to = [pkg for pkg in wrong_pkgs if pkg in module_artifacts]
            if belongs_to:
                logging.info(
                    "Wrong module packages belongs to '%s' module",
                    ":".join(str(el) for el in key),
                )


async def check_modules_in_errata_records():
    pulp = pulp_client.PulpClient(
        settings.pulp_host,
        settings.pulp_user,
        settings.pulp_password,
    )
    with SyncSession() as albs_db:
        platforms: typing.List[Platform] = (
            albs_db.execute(
                select(Platform)
                .where(Platform.is_reference.is_(False))
                .order_by(Platform.id),
            )
            .scalars()
            .all()
        )
        for platform in platforms:
            for repo in platform.repos:
                repo: Repository
                repo_name = (
                    f"{repo.name}-{repo.arch}{'-debuginfo' if repo.debug else ''}"
                )
                if not repo.production or repo.arch == "src" or repo.debug:
                    continue
                logging.info("Start checking %s", repo_name)
                module_index = await get_module_index(repo, repo_name)
                if not module_index:
                    continue
                repo_modules_cache = prepare_modules_cache(module_index)
                latest_repo_ver = await pulp.get_repo_latest_version(repo.pulp_href)
                repo_errata = await list_errata_pulp(latest_repo_ver, pulp)
                for errata in repo_errata:
                    if not errata["id"].startswith("ALSA"):
                        continue
                    find_wrong_modules_in_record(errata, repo_modules_cache)


async def main():
    pulp_client.PULP_SEMAPHORE = asyncio.Semaphore(10)
    await check_modules_in_errata_records()


if __name__ == "__main__":
    asyncio.run(main())

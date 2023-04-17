import argparse
import asyncio
import logging
import os.path
import pprint
import sys
import tempfile
import urllib.parse

sys.path.append(os.path.dirname(os.path.dirname(__file__)))

from alws.utils import pulp_client
from alws.utils.file_utils import download_big_file, hash_file
from alws.utils.parsing import parse_rpm_nevra
from scripts.utils.log import setup_logging
from scripts.utils.pulp import get_pulp_params

PROG_NAME = "packages-repo-uploader"


def parse_args(args):
    parser = argparse.ArgumentParser(PROG_NAME)
    parser.add_argument("-r", "--repository-name", required=True, type=str)
    parser.add_argument(
        "-p",
        "--package-links",
        nargs="+",
        required=True,
        type=str,
    )
    parser.add_argument("-v", "--verbose", action="store_true", default=False)
    return parser.parse_args(args)


async def create_rpm_package(
    logger: logging.Logger,
    pulp: pulp_client.PulpClient,
    file_name: str,
    artifact_href: str = "",
    file_path: str = "",
    checksum: str = "",
):
    if file_path and checksum:
        logger.info("Uploading %s to Pulp", file_path)
        artifact_href, _ = await pulp.upload_file(
            file_path=file_path,
            sha256=checksum,
        )
        logger.info("%s upload is finished", file_path)
    logger.info("Creating RPM package for %s", file_name)
    rpm_href = await pulp.create_rpm_package(file_name, artifact_href)
    logger.info("%s RPM package creation is finished", file_name)
    return rpm_href


async def async_main(args, work_dir, logger):
    pulp_client.PULP_SEMAPHORE = asyncio.Semaphore(5)
    pulp_host, pulp_user, pulp_password = get_pulp_params()
    pulp = pulp_client.PulpClient(pulp_host, pulp_user, pulp_password)
    repository = await pulp.get_rpm_repository(args.repository_name)
    if not repository:
        logger.error("Repository %s not found", args.repository_name)
        return

    logger.debug("Repository: %s", str(repository))
    rpm_package_hrefs = []
    coro_tasks = []

    for raw_link in args.package_links:
        link = urllib.parse.unquote(raw_link)
        file_name = os.path.basename(link.strip())
        nevra = parse_rpm_nevra(file_name)
        file_path = os.path.join(work_dir, file_name)
        logger.info("Downloading %s...", link)
        with open(file_path, "wb") as f:
            await download_big_file(link, f)
        logger.info("%s download is completed", file_name)

        checksum = hash_file(file_path, hash_type="sha256")
        logger.debug(
            "Check that such file already exists in Pulp: %s",
            file_name,
        )
        artifact_href = await pulp.check_if_artifact_exists(checksum)
        if not artifact_href:
            coro_tasks.append(
                create_rpm_package(
                    logger,
                    pulp,
                    file_name,
                    file_path=file_path,
                    checksum=checksum,
                ),
            )
            continue
        logger.debug(
            "Check that such RPM package already exists: %s",
            file_name,
        )
        rpms = await pulp.get_rpm_packages(
            include_fields=["sha256", "pulp_href", "artifact"],
            sha256=checksum,
        )
        if rpms:
            logger.debug("RPM package %s already exists", file_name)
            rpm_href = next(
                (
                    rpm["pulp_href"]
                    for rpm in rpms
                    if rpm["artifact"] == artifact_href
                ),
                None,
            )
            rpm_package_hrefs.append(rpm_href)
            continue
        logger.debug("Check RPM by NEVRA...")
        rpms = await pulp.get_rpm_packages(
            include_fields=["sha256", "pulp_href", "artifact"],
            name=nevra.name,
            version=nevra.version,
            release=nevra.release,
            arch=nevra.arch,
            epoch=nevra.epoch,
        )
        if not rpms:
            coro_tasks.append(
                create_rpm_package(
                    logger,
                    pulp,
                    file_name,
                    artifact_href=artifact_href,
                ),
            )
            continue
        rpm_href = next(
            (
                rpm["pulp_href"]
                for rpm in rpms
                if rpm["artifact"] == artifact_href
            ),
            None,
        )
        rpm_package_hrefs.append(rpm_href)
    rpm_package_hrefs.extend(await asyncio.gather(*coro_tasks))

    logger.debug(
        "RPM hrefs to add to repository: %s",
        pprint.pformat(rpm_package_hrefs, indent=4),
    )

    await pulp.modify_repository(
        repository["pulp_href"],
        rpm_package_hrefs,
    )
    if not repository["autopublish"]:
        await pulp.create_rpm_publication(repository["pulp_href"])


def main():
    arguments = parse_args(sys.argv[1:])
    setup_logging(verbose=arguments.verbose)
    logger = logging.getLogger(PROG_NAME)
    with tempfile.TemporaryDirectory(prefix=f"{PROG_NAME}_") as work_dir:
        asyncio.run(async_main(arguments, work_dir, logger))


if __name__ == "__main__":
    main()

import asyncio
import gzip
import logging
import os
import re
import sys
import urllib.parse
import uuid
from contextlib import asynccontextmanager

sys.path.append(os.path.dirname(os.path.dirname(__file__)))

import requests
from sqlalchemy import delete, select
from sqlalchemy.orm import selectinload

from alws.config import settings
from alws.dependencies import get_db, get_pulp_db
from alws.models import (
    Build,
    BuildTask,
    BuildTaskArtifact,
    Repository,
    TestTask,
)
from alws.pulp_models import (
    CoreContent,
    CoreContentArtifact,
    CoreRepositoryContent,
)
from alws.utils import pulp_client
from alws.utils.file_utils import hash_content

logging.basicConfig(
    format="%(asctime)s %(levelname)-8s %(message)s",
    level=logging.INFO,
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("albs-980.log"),
    ],
)

log_regex = re.compile(r'href="(?P<log_name>.+\.log)"')


async def main():
    pulp_client.PULP_SEMAPHORE = asyncio.Semaphore(5)
    pulp = pulp_client.PulpClient(
        settings.pulp_host,
        settings.pulp_user,
        settings.pulp_password,
    )

    def get_log_names_from_repo(repo: Repository):
        result = {}
        response = requests.get(repo.url)
        response.raise_for_status()
        for line in response.text.splitlines():
            regex_result = log_regex.search(line)
            if not regex_result:
                continue
            log_name = regex_result.group("log_name")
            result[log_name] = urllib.parse.urljoin(repo.url, log_name)
        return result

    async def download_log(url: str) -> bytes:
        response = requests.get(url)
        response.raise_for_status()
        return response.content

    async def process_old_log(log_name: str, url: str):
        content = await download_log(url)
        try:
            artifact_href, _ = await pulp.upload_file(gzip.compress(content))
        except Exception:
            # in case if we fall with the same artifact checksum
            artifact_href, _ = await pulp.upload_file(
                gzip.compress(
                    content + f"\n{log_name}\n".encode(),
                ),
            )
        log_href = await pulp.create_file(log_name, artifact_href)
        return log_name, log_href

    async def safe_delete(href: str):
        # some repositories can be already deleted in pulp
        try:
            await pulp.delete_by_href(href, wait_for_result=True)
        except Exception:
            logging.exception(
                "Cannot delete entity from pulp by href: %s",
                href,
            )

    async with asynccontextmanager(get_db)() as session:
        with get_pulp_db() as pulp_session:
            builds = (
                (
                    await session.execute(
                        select(Build)
                        .options(
                            selectinload(Build.repos),
                            selectinload(Build.tasks).selectinload(
                                BuildTask.artifacts.and_(
                                    BuildTaskArtifact.type == "build_log",
                                    BuildTaskArtifact.name.like("%.log"),
                                )
                            ),
                            selectinload(Build.tasks)
                            .selectinload(BuildTask.test_tasks)
                            .selectinload(TestTask.repository),
                            selectinload(Build.tasks)
                            .selectinload(BuildTask.test_tasks)
                            .selectinload(TestTask.artifacts),
                        )
                        .order_by(Build.id),
                    )
                )
                .scalars()
                .all()
            )
            repo_ids_to_remove = []
            for build in builds:
                logging.info("Processing build: %d", build.id)
                old_build_logs_repos = []
                old_test_logs_repos = []
                log_urls_mapping = {}
                new_build_logs_repo = None
                new_test_logs_repo = None
                build_artifacts = {}
                test_logs = []
                skip = False
                for build_task in build.tasks:
                    artifacts = [*build_task.artifacts]
                    for test_task in build_task.test_tasks:
                        repo_ids_to_remove.append(test_task.repository.id)
                        test_logs.append(test_task.repository)
                        artifacts.extend(test_task.artifacts)
                    build_artifacts.update(
                        {artifact.name: artifact for artifact in artifacts}
                    )

                for repo in build.repos + test_logs:
                    if repo.type == "build_log":
                        old_build_logs_repos.append(repo)
                    if repo.type == "test_log":
                        old_test_logs_repos.append(repo)
                    try:
                        log_urls_mapping.update(get_log_names_from_repo(repo))
                    except Exception:
                        skip = True
                        logging.exception(
                            "Cannot upload logs from: %s", repo.url
                        )

                if skip:
                    logging.info(
                        "Cannot upload logs from old repos, skipping build %d",
                        build.id,
                    )
                    continue
                build.repos = []
                for repo_type, repo_prefix in (
                    ("build_log", "build_logs"),
                    ("test_log", "test_logs"),
                ):
                    repo_name = f"build-{build.id}-{repo_type}"
                    # NOTE: left for debug, because we can't
                    # create repo with the same name

                    # log_repo = await pulp.get_log_repository(repo_name)
                    # if log_repo:
                    #     logging.info(
                    #         "\tRemoving existing new repo: %s",
                    #         log_repo["name"],
                    #     )
                    #     await safe_delete(log_repo["pulp_href"])
                    #     log_distr = await pulp.get_log_distro(repo_name)
                    #     if log_distr:
                    #         logging.info(
                    #             "\tRemoving existing new distr: %s",
                    #             log_distr["name"],
                    #         )
                    #         await safe_delete(log_distr["pulp_href"])

                    logging.info("\tCreating new log repo: %s", repo_name)
                    repo_url, repo_href = await pulp.create_log_repo(
                        repo_name,
                        distro_path_start=repo_prefix,
                    )
                    repo = Repository(
                        name=repo_name,
                        url=repo_url,
                        arch="log",
                        pulp_href=repo_href,
                        type=repo_type,
                        debug=False,
                    )
                    if repo_type == "build_log":
                        new_build_logs_repo = repo
                    else:
                        new_test_logs_repo = repo
                    build.repos.append(repo)

                # we need to update repositories for test_tasks
                for build_task in build.tasks:
                    for test_task in build_task.test_tasks:
                        test_task.repository = new_test_logs_repo

                # download, compress and upload logs
                logging.info("\tProcessing old build/test logs")
                compressed_logs_mapping = {}
                download_tasks = [
                    process_old_log(log_name, url)
                    for log_name, url in log_urls_mapping.items()
                    if log_name in build_artifacts
                ]
                for coro in asyncio.as_completed(download_tasks):
                    log_name, log_href = await coro
                    logging.info("\tLog %s is processed", log_name)
                    compressed_logs_mapping[log_name] = log_href
                    build_artifacts[log_name].href = log_href

                modify_tasks = []
                delete_tasks = []
                delete_distros = []
                for repos in (old_build_logs_repos, old_test_logs_repos):
                    if not repos:
                        continue
                    repo_type = repos[0].type
                    pulp_repo_ids, repo_hrefs = [], []
                    for repo in repos:
                        pulp_repo_ids.append(
                            uuid.UUID(repo.pulp_href.split("/")[-2]),
                        )
                        repo_hrefs.append(repo.pulp_href)
                        log_distr = await pulp.get_log_distro(repo.name)
                        if log_distr:
                            delete_distros.append(
                                safe_delete(log_distr["pulp_href"]),
                            )

                    subq = (
                        select(CoreRepositoryContent.content_id)
                        .where(
                            CoreRepositoryContent.repository_id.in_(
                                pulp_repo_ids
                            ),
                            CoreRepositoryContent.version_removed_id.is_(None),
                        )
                        .scalar_subquery()
                    )
                    query = select(CoreContent).where(
                        CoreContent.pulp_id.in_(subq),
                        CoreContent.pulp_type == "file.file",
                    )
                    repo_href_to_add = (
                        new_test_logs_repo.pulp_href
                        if repo_type == "test_log"
                        else new_build_logs_repo.pulp_href
                    )
                    artifacts = pulp_session.execute(query).scalars().all()
                    artifacts_mapping = {
                        artifact.pulp_id: artifact for artifact in artifacts
                    }
                    content_artifacts = pulp_session.execute(
                        select(CoreContentArtifact).where(
                            CoreContentArtifact.content_id.in_(
                                [art.pulp_id for art in artifacts]
                            )
                        )
                    )
                    # some artifacts can have the same relative_path
                    content_to_add = []
                    added_artifacts = []
                    for content_artifact in content_artifacts.scalars().all():
                        artifact = artifacts_mapping[
                            content_artifact.content_id
                        ]
                        if content_artifact.relative_path in added_artifacts:
                            continue
                        file_href = artifact.file_href
                        artifact_path = content_artifact.relative_path
                        if (
                            artifact_path.endswith(".log")
                            and artifact_path in compressed_logs_mapping
                        ):
                            file_href = compressed_logs_mapping[artifact_path]
                        added_artifacts.append(artifact_path)
                        content_to_add.append(file_href)

                    modify_tasks.append(
                        pulp.modify_repository(
                            repo_href_to_add,
                            add=content_to_add,
                        )
                    )
                    delete_tasks.extend(
                        [safe_delete(href) for href in repo_hrefs],
                    )
                logging.info("\tAdding logs into new repo")
                await asyncio.gather(*modify_tasks)
                logging.info("\tRemoving old repos")
                await asyncio.gather(*delete_tasks)
                logging.info("\tRemoving old distros")
                await asyncio.gather(*delete_distros)

            await session.execute(
                delete(Repository).where(
                    Repository.id.in_(repo_ids_to_remove),
                )
            )
            await session.commit()


if __name__ == "__main__":
    asyncio.run(main())

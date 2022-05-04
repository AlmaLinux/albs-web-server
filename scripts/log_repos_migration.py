import asyncio
from collections import defaultdict
import gzip
from io import BytesIO
import logging
import os
import re
import sys
import typing
import urllib.parse

from sqlalchemy import select, delete, insert
from sqlalchemy.orm import selectinload

sys.path.append(os.path.dirname(os.path.dirname(__file__)))

from alws import models
from alws.constants import LOG_REPO_ARCH
from alws.config import settings
from alws.database import SyncSession
from alws.config import settings
from alws.utils.file_utils import download_file
from alws.utils.pulp_client import PulpClient


def get_full_url(endpoint: str) -> str:
    return urllib.parse.urljoin(settings.pulp_host, endpoint)


async def compress_old_log(pulp_client: PulpClient, url: str) -> str:
    host = 'http://localhost:8080'
    # host = settings.pulp_host
    temp_log = BytesIO()
    await download_file(urllib.parse.urljoin(host, url), temp_log)
    href, _ = await pulp_client.upload_file(gzip.compress(temp_log.read()))
    return href


async def find_old_log_repos(
    pulp_client: PulpClient,
) -> typing.Tuple[
    typing.Dict[int, typing.List[str]],
    typing.Dict[str, typing.List[str]],
    typing.Dict[int, typing.List[str]],
]:
    fields = ','.join(('name', 'pulp_href', 'latest_version_href'))
    url = get_full_url(f'pulp/api/v3/repositories/file/file/?fields={fields}')
    build_log_repos_mapping = defaultdict(list)
    test_log_repos_by_build_task = defaultdict(list)
    builds_mapping = defaultdict(list)
    hrefs_to_delete = defaultdict(list)
    async for repo in pulp_client.iter_repo(url):
        repo_name = repo['name']
        is_test = 'test_logs' in repo_name
        build_repo = re.search(r'(\d+)-artifacts-(\d+)$', repo_name)
        test_repo = re.search(r'(\d+)-tr-(\d+)$', repo_name)
        if not any((build_repo, test_repo)):
            continue
        latest_repo_data = await pulp_client.get_latest_repo_present_content(
            repo['latest_version_href'])
        file_repo_href = latest_repo_data.get('file.file', {}).get('href')
        hrefs_to_delete['repos'].append(repo['pulp_href'])
        if file_repo_href is None:
            continue
        artifacts_to_add = []
        tasks = []
        async for artifact in pulp_client.iter_repo(file_repo_href):
            file_name = artifact['relative_path']
            full_url = f'pulp/content/build_logs/{repo_name}/{file_name}'
            if is_test:
                full_url = f'pulp/content/test_logs/{repo_name}/{file_name}'
            # full_url = get_full_url(url)
            if artifact['name'].endswith('.log'):
                tasks.append(compress_old_log(pulp_client, full_url))
                hrefs_to_delete['logs'].append(artifact['pulp_href'])
                continue
            artifacts_to_add.append(artifact['pulp_href'])
        artifacts_to_add.extend(await asyncio.gather(*tasks))
        build_id = None
        build_task_id = None
        if build_repo is not None:
            build_id, build_task_id = build_repo.groups()
            build_log_repos_mapping[build_id].extend(artifacts_to_add)
            builds_mapping[build_id].append(build_task_id)
        else:
            build_task_id, _ = test_repo.groups()
            test_log_repos_by_build_task[build_task_id].extend(
                artifacts_to_add)
    for build_task_id, test_artifacts in test_log_repos_by_build_task.items():
        build_id = next((
            build_id
            for build_id, build_task_ids in builds_mapping.items()
            if build_task_id in build_task_ids
        ), None)
        if build_id is None:
            continue
        build_log_repos_mapping[build_id].extend(test_artifacts)
    return build_log_repos_mapping, hrefs_to_delete, builds_mapping


async def delete_old_file_distros(pulp_client: PulpClient) -> list:
    url = get_full_url('pulp/api/v3/distributions/file/file/?fields=pulp_href')
    delete_tasks = (
        pulp_client.delete_by_href(distr['pulp_href'], wait_for_result=True)
        async for distr in pulp_client.iter_repo(url)
    )
    return await asyncio.gather(*delete_tasks)


async def create_log_repo(
    pulp_client: PulpClient,
    build_id: int,
) -> typing.Tuple[int, models.Repository]:
    repo_name = f'{build_id}-artifacts'
    repo_url, pulp_href = await pulp_client.create_log_repo(repo_name)
    repository = models.Repository(
        name=repo_name,
        url=repo_url,
        arch=LOG_REPO_ARCH,
        pulp_href=pulp_href,
        type='build_log',
        debug=False,
    )
    return build_id, repository


async def main():
    pulp_client = PulpClient(
        settings.pulp_host,
        settings.pulp_user,
        settings.pulp_password,
    )
    logger = logging.getLogger('log-repo-migration')
    logging.basicConfig(level=logging.INFO)
    logger.info('Start preparing data for create/update/delete olg log repos')
    new_logs_data, hrefs_to_delete, builds_mapping = await find_old_log_repos(
        pulp_client)
    build_task_ids = []
    for ids in builds_mapping.values():
        build_task_ids.extend(ids)
    logger.info('Preparing is finishing')

    logger.info('Start creating new log repos in pulp')
    new_repos_data = await asyncio.gather(*(
        create_log_repo(pulp_client, build_id)
        for build_id in new_logs_data
    ))
    new_repos_data = dict(new_repos_data)
    logger.info('Creating log repos in pulp is finished')

    logger.info('Start inserting old build/tests artifacts in new pulp repos')
    await asyncio.gather(*(
        pulp_client.modify_repository(repository.pulp_href,
                                      add=list(set(new_logs_data[build_id])))
        for build_id, repository in new_repos_data.items()
    ))
    logger.info(
        'Inserting old build/tests artifacts in new pulp repos is finished')

    with SyncSession() as db:
        with db.begin():
            repo_ids_to_delete = db.execute(
                select(models.Repository.id).where(
                    models.Repository.pulp_href.in_(hrefs_to_delete['repos']),
                ),
            )
            repo_ids_to_delete = repo_ids_to_delete.scalars().all()
            logger.info('Start inserting new repos into DB')
            db.add_all(new_repos_data.values())
            db.flush()
            insert_values = []
            for build_id, repo in new_repos_data.items():
                insert_values.append({'build_id': build_id,
                                      'repository_id': repo.id})
            db.execute(insert(models.BuildRepo), insert_values)
            db.flush()
            logger.info('Inserting new repos into DB is finished')
            logger.info('Start deleting old repos from DB')
            test_tasks = db.execute(
                select(models.TestTask).where(
                    models.TestTask.build_task_id.in_(build_task_ids),
                ).options(selectinload(models.TestTask.build_task)),
            )
            for test_task in test_tasks.scalars().all():
                new_repo = new_repos_data.get(test_task.build_task.build_id)
                if new_repo is None:
                    continue
                test_task.repository_id = new_repo.id
            db.flush()
            db.execute(
                delete(models.BuildRepo).where(
                    models.BuildRepo.c.repository_id.in_(repo_ids_to_delete),
                ),
            )
            db.execute(
                delete(models.Repository).where(
                    models.Repository.id.in_(repo_ids_to_delete),
                ),
            )
            db.commit()
            logger.info('Deleting old repos from DB is completed')

    logger.info('Start deleting old file distros')
    deleted_file_distros = len(await delete_old_file_distros(pulp_client))
    logger.info('Total deleted file distros: %s', deleted_file_distros)

    logger.info('Start deleting old file repos and logs')
    delete_tasks = []
    for key in ('repos', 'logs'):
        delete_tasks.extend((
            pulp_client.delete_by_href(repo_href, wait_for_result=True)
            for repo_href in hrefs_to_delete[key]
        ))
    await asyncio.gather(*delete_tasks)
    logger.info('Deleting old file repos and logs is completed')


if __name__ == '__main__':
    asyncio.run(main())

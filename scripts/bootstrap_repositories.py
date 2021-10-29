import os
import sys

from alws.utils.pulp_client import PulpClient

sys.path.append(os.path.dirname(__file__))

import argparse
import asyncio
import logging

import yaml

from alws import crud, dependencies
from alws.schemas import remote_schema, repository_schema


def parse_args():
    parser = argparse.ArgumentParser(
        'bootstrap_repositories',
        description='Repository bootstrap script. Creates repositories '
                    'in Pulp for further usage')
    parser.add_argument(
        '-R', '--no-remotes', action='store_true', default=False, type=bool,
        required=False, help='Disable creation of repositories remotes')
    parser.add_argument(
        '-S', '--no-sync', action='store_true', default=False, type=bool,
        required=False, help='Do not sync repositories with '
                             'corresponding remotes')
    parser.add_argument(
        '-c', '--config', type=str, required=True,
        help='Path to config file with repositories description')
    parser.add_argument('-v', '--verbose', action='store_true', default=False,
                        type=bool, required=False, help='Enable verbose output')
    return parser.parse_args()


def main():
    pulp_host = os.environ['PULP_HOST']
    pulp_user = os.environ['PULP_USER']
    pulp_password = os.environ['PULP_PASSWORD']
    args = parse_args()
    logger = logging.getLogger(__name__)
    config_path = os.path.expanduser(os.path.expandvars(args.config))
    with open(config_path, 'rt') as f:
        loader = yaml.Loader(f)
        platform_data = loader.get_data()

    if not platform_data.get('repositories'):
        logger.error('Config does not contain a list of repositories')
        return 1

    pulp_client = PulpClient(pulp_host, pulp_user, pulp_password)
    db = asyncio.run(dependencies.get_db())

    for repo_info in platform_data.get('repositories'):
        logger.info('Creating repository from the following data: %s',
                    str(repo_info))
        # If repository is not marked as production, do not remove `url` field
        repo_name = repo_info['name']
        is_production = repo_info.get('production', False)
        repo_sync_policy = repo_info.pop('repository_sync_policy', None)
        remote_sync_policy = repo_info.pop('remote_sync_policy', None)
        if is_production:
            repo_payload = repo_info.copy()
            repo_payload.pop('url')
            repo_url, repo_href = asyncio.run(
                pulp_client.create_rpm_repository(
                    repo_name, create_publication=True)
            )
            logger.debug('Base URL: %s, Pulp href: %s', repo_url, repo_href)
            payload_dict = repo_payload.copy()
            payload_dict['url'] = repo_url
            payload_dict['pulp_href'] = repo_href
            repository = asyncio.run(crud.create_repository(
                db, repository_schema.RepositoryCreate(**payload_dict)))
        else:
            repository = asyncio.run(crud.create_repository(
                db, repository_schema.RepositoryCreate(**repo_info)))

        repo_repr = str(repository)
        logger.debug('Repository instance: %s', repo_repr)
        if args.no_remotes:
            logger.warning('Not creating a remote for repository %s', repo_repr)
            continue
        if not is_production:
            logger.info('Repository %s is not marked as production and '
                        'does not need remote setup')
            continue

        remote_payload = repo_info.copy()
        remote_payload.pop('type', None)
        remote_payload.pop('debug', False)
        remote_payload.pop('production', False)
        remote_payload['policy'] = remote_sync_policy
        remote = asyncio.run(crud.create_repository_remote(
            db, remote_schema.RemoteCreate(**remote_payload)))
        remote_repr = str(remote)

        if args.no_sync:
            logger.info('Synchronization from remote is disabled, skipping')
            continue
        logger.info('Syncing %s from %s...', repo_repr, remote_repr)
        asyncio.run(pulp_client.sync_rpm_repo_from_remote(
            repository.pulp_href, remote.pulp_href, sync_policy=repo_sync_policy,
            wait_for_result=True))
        logger.info('Repository %s sync is completed', repo_repr)

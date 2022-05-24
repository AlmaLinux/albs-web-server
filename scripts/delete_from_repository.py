import argparse
import logging
import os
import pprint
import sys
import time
from urllib.parse import urljoin

import requests
from requests.auth import HTTPBasicAuth
from sqlalchemy.future import select

sys.path.append(os.path.dirname(os.path.dirname(__file__)))

from alws import models
from alws.config import settings
from alws.database import SyncSession


PROG_NAME = 'packages-repo-deleter'


class RepositoryNotFound(ValueError):
    pass


def parse_args(args):
    parser = argparse.ArgumentParser('packages-repo-deleter')
    parser.add_argument('-r', '--repository-name', required=True, type=str)
    parser.add_argument('-a', '--architecture', required=True, type=str)
    parser.add_argument('-p', '--packages', nargs='+', required=True, type=str)
    parser.add_argument('-v', '--verbose', action='store_true', default=False)
    return parser.parse_args(args)


def get_repository(repo_name: str, arch: str) -> models.Repository:
    with SyncSession() as session:
        repo = (session.execute(select(models.Repository)
                                .where(models.Repository.name == repo_name,
                                       models.Repository.arch == arch))
                .scalars().first())
        if not repo:
            raise RepositoryNotFound(f'Repository {repo_name} is not found')
        return repo


def wait_for_task(base_url: str, task_href: str, auth: HTTPBasicAuth,
                  logger: logging.Logger):
    task_url = urljoin(base_url, task_href)
    logger.info('Waiting for task %s to finish', task_href)
    res = requests.get(task_url, auth=auth).json()
    while res['state'] not in ('failed', 'completed'):
        logger.debug('Still in progress...')
        time.sleep(3)
        res = requests.get(task_url, auth=auth).json()
    logger.info('Task %s is finished', task_href)
    return res


def publish_repo(base_url: str, repo_href: str, auth: HTTPBasicAuth,
                 logger: logging.Logger):
    full_url = urljoin(base_url, '/pulp/api/v3/publications/rpm/rpm/')
    task_href = requests.post(
        full_url, json={'repository': repo_href}, auth=auth).json()['task']
    return wait_for_task(base_url, task_href, auth, logger)


def setup_logging(verbose: bool = False):
    log_level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(format='%(asctime)s %(levelname)-8s %(message)s',
                        level=log_level, datefmt='%Y-%m-%d %H:%M:%S')


def main():
    packages_endpoint = '/pulp/api/v3/content/rpm/packages/'
    arguments = parse_args(sys.argv[1:])
    setup_logging(verbose=arguments.verbose)
    logger = logging.getLogger(PROG_NAME)
    pulp_auth = HTTPBasicAuth(
        settings.pulp_user, settings.pulp_password)
    pulp_host = settings.pulp_host

    repo = get_repository(
        arguments.repository_name, arguments.architecture)
    logger.debug('Repository: %s', repo)
    repo_info = requests.get(
        urljoin(pulp_host, repo.pulp_href), auth=pulp_auth).json()
    # Looking for packages that belong to the latest repository version
    query_params = {
        'repository_version': repo_info['latest_version_href'],
        'fields': ['location_href', 'pulp_href'],
    }
    # Check how many packages is in the repo to get them the in 1 request
    logger.info('Getting repository packages')
    pulp_response = requests.get(
        urljoin(pulp_host, packages_endpoint), params=query_params,
        auth=pulp_auth).json()
    package_count = pulp_response['count']
    repo_packages = pulp_response['results']
    logger.debug('Packages count: %d', package_count)
    if package_count > 100:
        query_params['limit'] = package_count + 1
        repo_packages = requests.get(
            urljoin(pulp_host, packages_endpoint),
            params=query_params, auth=pulp_auth).json()['results']
    logger.info('Got all packages')

    logger.info('Compiling list of packages hrefs to delete')
    to_remove = []
    # location href may be weird, so we need double loop
    # to properly detect packages being in the repo
    for pkg in arguments.packages:
        for pulp_pkg in repo_packages:
            if pkg == pulp_pkg['location_href'] \
                    or pkg in pulp_pkg['location_href']:
                to_remove.append(pulp_pkg['pulp_href'])
    logger.info('List is compiled')
    logger.debug('Packages to delete: %s', pprint.pformat(to_remove, indent=4))

    if not to_remove:
        logger.warning('Nothing to delete, packages %s'
                       ' were not found in the repository',
                       str(arguments.packages))
        return

    modify_url = urljoin(urljoin(pulp_host, repo.pulp_href), 'modify/')
    task_href = requests.post(
        modify_url, auth=pulp_auth,
        json={'remove_content_units': to_remove}).json()['task']
    task_result = wait_for_task(pulp_host, task_href, pulp_auth, logger)
    if task_result['state'] == 'failed':
        logger.error('Packages deletion failed: %s',
                     pprint.pformat(task_result, indent=4))
        return
    logger.info('Packages deletion succeeded')

    # Production repositories need to be published separately,
    # every other repository will be published automatically upon modification
    if repo.production:
        logger.info('Publishing new repository version')
        publication_result = publish_repo(pulp_host, repo.pulp_href, pulp_auth,
                                          logger)
        if publication_result['state'] == 'failed':
            logger.error('Repository publication failed: %s',
                         pprint.pformat(publication_result, indent=4))
            return
        logger.info('Repository is published successfully')


if __name__ == '__main__':
    main()

import logging
import os
import pprint
import time
import typing
from urllib.parse import urljoin

import requests
from requests.auth import HTTPBasicAuth


__all__ = [
    'get_repository',
    'get_repository_packages',
    'get_pulp_params',
    'match_packages',
    'publish_repository',
    'wait_for_task',
]


def get_pulp_params() -> typing.Tuple[str, str, str]:
    pulp_host = os.environ['PULP_HOST']
    pulp_user = os.environ['PULP_USER']
    pulp_password = os.environ['PULP_PASSWORD']
    return pulp_host, pulp_user, pulp_password


def wait_for_task(base_url: str, task_href: str, auth: HTTPBasicAuth,
                  logger: logging.Logger):
    task_url = urljoin(base_url, task_href)
    logger.info('Waiting for task %s to finish', task_href)
    res = requests.get(task_url, auth=auth).json()
    while res['state'] not in ('failed', 'completed'):
        logger.debug('Still in progress...')
        time.sleep(10)
        res = requests.get(task_url, auth=auth).json()
    logger.info('Task %s is finished', task_href)
    return res


def publish_repository(base_url: str, repo_info: dict, auth: HTTPBasicAuth,
                       logger: logging.Logger):
    auto_publish = repo_info.get('autopublish', False)
    logger.debug('Auto publish: %s', str(auto_publish))
    if auto_publish:
        logger.debug(
            'Nothing to publish, repository is set for automatic publishing')
        return
    logger.info('Publishing new repository version')
    full_url = urljoin(base_url, '/pulp/api/v3/publications/rpm/rpm/')
    repo_href = repo_info['pulp_href']
    task_href = requests.post(
        full_url, json={'repository': repo_href}, auth=auth).json()['task']
    logger.info('Repository is published successfully')
    task_res = wait_for_task(base_url, task_href, auth, logger)
    if task_res['state'] == 'failed':
        logger.error('Repository publication failed: %s',
                     pprint.pformat(task_res, indent=4))
        return
    logger.info('Repository is published successfully')


def get_repository(base_url: str, repo_name: str,
                   auth: HTTPBasicAuth) -> typing.Optional[dict]:
    full_url = urljoin(base_url, '/pulp/api/v3/repositories/rpm/rpm/')
    params = {'name': repo_name}
    result = requests.get(full_url, params=params, auth=auth).json()
    if result['count'] == 0:
        return None
    return result['results'][0]


def get_repository_packages(base_url: str, auth: HTTPBasicAuth,
                            query_params: dict,
                            logger: logging.Logger) -> typing.List[dict]:
    packages_endpoint = '/pulp/api/v3/content/rpm/packages/'
    # Check how many packages is in the repo to get them the in 1 request
    logger.info('Getting repository packages')
    pulp_response = requests.get(
        urljoin(base_url, packages_endpoint), params=query_params,
        auth=auth).json()
    package_count = pulp_response['count']
    repo_packages = pulp_response['results']
    logger.debug('Packages count: %d', package_count)
    if package_count > 100:
        query_params['limit'] = package_count + 1
        repo_packages = requests.get(
            urljoin(base_url, packages_endpoint),
            params=query_params, auth=auth).json()['results']
    logger.info('Got all packages')
    return repo_packages


def match_packages(packages_names: typing.List[str],
                   repository_packages: typing.List[dict]) -> typing.List[str]:
    result = []
    for pkg in packages_names:
        for pulp_pkg in repository_packages:
            if pkg == pulp_pkg['location_href'] \
                    or pkg in pulp_pkg['location_href']:
                result.append(pulp_pkg['pulp_href'])
    return result

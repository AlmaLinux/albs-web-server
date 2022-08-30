import argparse
import logging
import pprint
import sys
from urllib.parse import urljoin

import requests
from requests.auth import HTTPBasicAuth

from scripts.utils.log import setup_logging
from scripts.utils.pulp import (
    get_repository,
    get_repository_packages,
    get_pulp_params,
    match_packages,
    publish_repository,
    wait_for_task,
)

PROG_NAME = 'copy-packages'


def parse_args(args):
    parser = argparse.ArgumentParser(PROG_NAME)
    parser.add_argument('-f', '--repo-from', type=str, required=True,
                        help='Repository name to copy packages from')
    parser.add_argument('-t', '--repo-to', type=str, required=True,
                        help='Repository name to copy packages to')
    parser.add_argument('-p', '--packages', nargs='+', required=True,
                        action='extend', type=str)
    parser.add_argument('-v', '--verbose', action='store_true', default=False)
    return parser.parse_args(args)


def main():
    arguments = parse_args(sys.argv[1:])
    setup_logging(verbose=arguments.verbose)
    logger = logging.getLogger(PROG_NAME)
    logger.debug('Packages: %s', str(arguments.packages))
    pulp_host, pulp_user, pulp_password = get_pulp_params()
    pulp_auth = HTTPBasicAuth(pulp_user, pulp_password)

    repo_from = get_repository(pulp_host, arguments.repo_from, pulp_auth)
    repo_to = get_repository(pulp_host, arguments.repo_to, pulp_auth)
    logger.debug('From where to copy info: %s',
                 pprint.pformat(repo_to, indent=4))
    logger.debug('Where to copy info: %s', pprint.pformat(repo_to, indent=4))
    query_params = {
        'repository_version': repo_from['latest_version_href'],
        'fields': ['location_href', 'pulp_href'],
    }
    repo_packages = get_repository_packages(
        pulp_host, pulp_auth, query_params, logger)
    packages_to_copy = match_packages(arguments.packages, repo_packages)

    if not packages_to_copy:
        logger.warning('Nothing to copy, packages %s'
                       ' were not found in the repository',
                       str(arguments.packages))
        return

    logger.debug('Packages that will be copied: %s',
                 pprint.pformat(packages_to_copy, indent=4))
    modify_url = urljoin(urljoin(pulp_host, repo_to['pulp_href']), 'modify/')
    task_href = requests.post(
        modify_url, auth=pulp_auth,
        json={'add_content_units': packages_to_copy}).json()['task']
    task_result = wait_for_task(pulp_host, task_href, pulp_auth, logger)
    if task_result['state'] == 'failed':
        logger.error('Packages copy failed: %s',
                     pprint.pformat(task_result, indent=4))
        return
    logger.info('Packages copy succeeded')

    publish_repository(pulp_host, repo_to, pulp_auth, logger)


if __name__ == '__main__':
    main()

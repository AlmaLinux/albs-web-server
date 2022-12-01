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


PROG_NAME = 'packages-repo-deleter'


def parse_args(args):
    parser = argparse.ArgumentParser(PROG_NAME)
    parser.add_argument('-r', '--repository-name', required=True, type=str)
    parser.add_argument('-p', '--packages', nargs='+', required=True,
                        type=str)
    parser.add_argument('-v', '--verbose', action='store_true', default=False)
    return parser.parse_args(args)


def main():
    arguments = parse_args(sys.argv[1:])
    setup_logging(verbose=arguments.verbose)
    logger = logging.getLogger(PROG_NAME)
    pulp_host, pulp_user, pulp_password = get_pulp_params()
    pulp_auth = HTTPBasicAuth(pulp_user, pulp_password)

    repo = get_repository(pulp_host, arguments.repository_name, pulp_auth)
    if not repo:
        logger.error('Repository %s not found', arguments.repository_name)
        return

    logger.debug('Repository: %s', str(repo))
    # Looking for packages that belong to the latest repository version
    query_params = {
        'repository_version': repo['latest_version_href'],
        'fields': ['location_href', 'pulp_href'],
    }
    # Check how many packages is in the repo to get them the in 1 request
    logger.info('Getting repository packages')
    repo_packages = get_repository_packages(
        pulp_host, pulp_auth, query_params, logger)
    logger.info('Got all packages')

    logger.info('Compiling list of packages hrefs to delete')
    to_remove = match_packages(arguments.packages, repo_packages)
    logger.info('List is compiled')
    logger.debug('Packages to delete: %s', pprint.pformat(to_remove, indent=4))

    if not to_remove:
        logger.warning('Nothing to delete, packages %s'
                       ' were not found in the repository',
                       str(arguments.packages))
        return

    modify_url = urljoin(urljoin(pulp_host, repo['pulp_href']), 'modify/')
    task_href = requests.post(
        modify_url, auth=pulp_auth,
        json={'remove_content_units': to_remove}).json()['task']
    task_result = wait_for_task(pulp_host, task_href, pulp_auth, logger)
    if task_result['state'] == 'failed':
        logger.error('Packages deletion failed: %s',
                     pprint.pformat(task_result, indent=4))
        return
    logger.info('Packages deletion succeeded')

    publish_repository(pulp_host, repo, pulp_auth, logger)


if __name__ == '__main__':
    main()

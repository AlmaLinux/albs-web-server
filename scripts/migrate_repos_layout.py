"""
Switches the package layout of production and product RPM repositories
in Pulp, see https://github.com/AlmaLinux/build-system/issues/554

pulp_rpm applies a repository layout only to publications created after
the change, so each migrated repository is republished as well unless
--no-publish is passed. The script is idempotent: repositories that already
have the layout and whose latest publication uses it are left untouched.
"""

import asyncio
import logging
import os
import sys
from argparse import ArgumentParser
from dataclasses import dataclass
from typing import List, Optional

sys.path.append(os.path.dirname(os.path.dirname(__file__)))

from sqlalchemy import select

from alws import models
from alws.config import settings
from alws.constants import RpmRepositoryLayout
from alws.dependencies import get_async_db_session
from alws.utils.fastapi_sqla_setup import setup_all
from alws.utils.pulp_client import PulpClient, get_pulp_client

EXIT_OK = 0
EXIT_ERROR = 1

RPM_REPOSITORIES_PATH = 'repositories/rpm/rpm/'
RPM_PUBLICATIONS_ENDPOINT = 'pulp/api/v3/publications/rpm/rpm/'

logger = logging.getLogger('repos-layout-migrator')


@dataclass
class MigrationResult:
    name: str
    layout_updated: bool = False
    republished: bool = False


def parse_args():
    parser = ArgumentParser(
        'migrate_repos_layout',
        description=(
            'Switches the package layout of production and product RPM '
            'repositories in Pulp and republishes them'
        ),
    )
    parser.add_argument(
        '-l',
        '--layout',
        choices=[layout.value for layout in RpmRepositoryLayout],
        default=settings.pulp_production_repo_layout.value,
        help='target package layout (default: %(default)s)',
    )
    parser.add_argument(
        '-p',
        '--platform',
        dest='platforms',
        action='append',
        help='only migrate repositories of the platform, can be repeated',
    )
    parser.add_argument(
        '-P',
        '--product',
        dest='products',
        action='append',
        help='only migrate repositories of the product, can be repeated',
    )
    parser.add_argument(
        '-r',
        '--repo-id',
        dest='repo_ids',
        type=int,
        action='append',
        help='only migrate the repository with the ID, can be repeated',
    )
    parser.add_argument(
        '--no-publish',
        dest='publish',
        action='store_false',
        help=(
            'only update the repositories layout, they switch to it at their '
            'next regular publication'
        ),
    )
    parser.add_argument(
        '-c',
        '--concurrency',
        type=int,
        default=4,
        help=(
            'how many repositories are migrated at the same time '
            '(default: %(default)s)'
        ),
    )
    parser.add_argument('-d', '--dry-run', action='store_true')
    parser.add_argument('-v', '--verbose', action='store_true')
    return parser.parse_args()


async def get_repository_hrefs(
    platforms: Optional[List[str]] = None,
    products: Optional[List[str]] = None,
    repo_ids: Optional[List[int]] = None,
) -> List[str]:
    """
    Returns Pulp hrefs of the production RPM repositories.
    Product repositories are stored as production ones too.
    Filters are combined, so a repository has to match all of them.
    """
    query = select(models.Repository.pulp_href).where(
        models.Repository.production.is_(True),
        models.Repository.pulp_href.contains(RPM_REPOSITORIES_PATH),
    )
    if platforms:
        query = (
            query.join(
                models.PlatformRepo,
                models.PlatformRepo.c.repository_id == models.Repository.id,
            )
            .join(
                models.Platform,
                models.Platform.id == models.PlatformRepo.c.platform_id,
            )
            .where(models.Platform.name.in_(platforms))
        )
    if products:
        query = (
            query.join(
                models.ProductRepositories,
                models.ProductRepositories.c.repository_id
                == models.Repository.id,
            )
            .join(
                models.Product,
                models.Product.id == models.ProductRepositories.c.product_id,
            )
            .where(models.Product.name.in_(products))
        )
    if repo_ids:
        query = query.where(models.Repository.id.in_(repo_ids))
    async with get_async_db_session() as session:
        result = await session.execute(query.distinct())
    return sorted(result.scalars().all())


async def get_published_layout(
    pulp: PulpClient,
    version_href: str,
) -> Optional[str]:
    """
    Returns the layout of the newest publication of the repository version,
    i.e. the one its distribution serves.
    """
    response = await pulp.request(
        'GET',
        RPM_PUBLICATIONS_ENDPOINT,
        params={
            'repository_version': version_href,
            'ordering': '-pulp_created',
            'limit': 1,
            'fields': 'layout',
        },
    )
    if not response['results']:
        return None
    return response['results'][0].get('layout')


async def migrate_repository(
    pulp: PulpClient,
    repo_href: str,
    layout: str,
    publish: bool = True,
    dry_run: bool = False,
) -> MigrationResult:
    repo = await pulp.get_by_href(repo_href)
    result = MigrationResult(name=repo['name'])
    if repo.get('layout') == layout:
        logger.debug('%s already has %s layout', result.name, layout)
    else:
        logger.info(
            '%sUpdating %s layout: %s -> %s',
            '[dry-run] ' if dry_run else '',
            result.name,
            repo.get('layout'),
            layout,
        )
        if not dry_run:
            await pulp.update_rpm_repository(repo_href, layout=layout)
        result.layout_updated = True

    if not publish:
        return result
    published_layout = await get_published_layout(
        pulp, repo['latest_version_href']
    )
    if published_layout == layout:
        logger.debug(
            '%s is already published with %s layout', result.name, layout
        )
        return result
    logger.info(
        '%sRepublishing %s, current publication layout: %s',
        '[dry-run] ' if dry_run else '',
        result.name,
        published_layout,
    )
    if not dry_run:
        await pulp.create_rpm_publication(repo_href)
    result.republished = True
    return result


async def migrate_repositories(
    pulp: PulpClient,
    repo_hrefs: List[str],
    layout: str,
    publish: bool = True,
    dry_run: bool = False,
    concurrency: int = 4,
) -> List[Optional[MigrationResult]]:
    """
    Migrates the repositories, a failed one results in None
    so the others are still processed.
    """
    semaphore = asyncio.Semaphore(max(concurrency, 1))

    async def bounded(repo_href: str) -> Optional[MigrationResult]:
        async with semaphore:
            try:
                return await migrate_repository(
                    pulp,
                    repo_href,
                    layout,
                    publish=publish,
                    dry_run=dry_run,
                )
            except Exception:
                logger.exception('Cannot migrate repository %s', repo_href)
                return None

    return await asyncio.gather(*(bounded(href) for href in repo_hrefs))


async def main() -> int:
    args = parse_args()
    log_level = logging.DEBUG if args.verbose else logging.INFO
    logging.basicConfig(level=log_level)
    logger.setLevel(log_level)
    await setup_all()
    repo_hrefs = await get_repository_hrefs(
        platforms=args.platforms,
        products=args.products,
        repo_ids=args.repo_ids,
    )
    if not repo_hrefs:
        logger.warning('No repositories match the given filters')
        return EXIT_OK
    logger.info('Found %d repositories to check', len(repo_hrefs))
    results = await migrate_repositories(
        get_pulp_client(),
        repo_hrefs,
        args.layout,
        publish=args.publish,
        dry_run=args.dry_run,
        concurrency=args.concurrency,
    )
    succeeded = [result for result in results if result]
    failed = len(results) - len(succeeded)
    logger.info(
        '%sDone: %d checked, %d layout updated, %d republished, %d failed',
        '[dry-run] ' if args.dry_run else '',
        len(results),
        sum(result.layout_updated for result in succeeded),
        sum(result.republished for result in succeeded),
        failed,
    )
    return EXIT_ERROR if failed else EXIT_OK


if __name__ == '__main__':
    sys.exit(asyncio.run(main()))

import os
import sys
import typing
import argparse
import logging

from syncer import sync
from pathlib import Path
from plumbum import local
from sqlalchemy.future import select
from sqlalchemy.orm import selectinload

sys.path.append(os.path.dirname(os.path.dirname(__file__)))


from alws import database
from alws import models
from alws.utils.exporter import fs_export_repository
from repomd_signer import repomd_signer


def parse_args():
    parser = argparse.ArgumentParser(
        'packages_exporter',
        description='Packages exporter script. Exports repositories from Pulp'
                    'and transfer them to production host'
    )
    parser.add_argument('platform_names', type=str, nargs='+')
    parser.add_argument('-v', '--verbose', action='store_true', default=False,
                        required=False, help='Enable verbose output')
    return parser.parse_args()


async def export_repos_from_pulp(platform_names: typing.List[str]):
    repo_ids = []
    platforms_dict = {}
    async with database.Session() as db:
        db_platforms = await db.execute(
            select(models.Platform).where(
                models.Platform.name.in_(platform_names)).options(
                    selectinload(models.Platform.repos))
        )
        db_platforms = db_platforms.scalars().all()
        for db_platform in db_platforms:
            platforms_dict[db_platform.name] = db_platform.id
            repo_ids.extend((
                repo.id for repo in db_platform.repos
                if repo.production is True
            ))
    return (await fs_export_repository(db=db, repository_ids=set(repo_ids)),
            platforms_dict)


def main():
    args = parse_args()
    logger = logging.getLogger('packages-exporter')
    if args.verbose:
        logging.basicConfig(level=logging.DEBUG)
    else:
        logging.basicConfig(level=logging.INFO)

    logger.info('Start exporting packages for following platforms:\n%s',
                args.platform_names)
    exported_paths, platforms_dict = sync(export_repos_from_pulp(
        args.platform_names))
    logger.info('All repositories exported in following paths:\n%s',
                '\n'.join((str(path) for path in exported_paths)))

    createrepo_c = local['createrepo_c']
    modifyrepo_c = local['modifyrepo_c']
    for exp_path in exported_paths:
        path = Path(exp_path)
        repo_path = path.parent
        repodata = repo_path / 'repodata'
        modules_yaml = repodata / 'modules.yaml'
        if modules_yaml.exists():
            modifyrepo_c(modules_yaml, repodata)
        try:
            repomd_signer(repodata, platforms_dict)
        except Exception as exc:
            logger.exception('Cannot to sign repomd.xml:')
        else:
            logger.info('repomd.xml in %s is signed', str(repodata))


if __name__ == '__main__':
    main()

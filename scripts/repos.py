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
    parser.add_argument('platform_name', type=str, nargs='+')
    parser.add_argument('-v', '--verbose', action='store_true', default=False,
                        required=False, help='Enable verbose output')
    return parser.parse_args()


async def export_repos_from_pulp(platform_names: typing.List[str]):
    async with database.Session() as db:
        repo_ids = []
        for platform_name in platform_names:
            result = await db.execute(select(models.Platform.id).filter(
                models.Platform.name.ilike(f'%{platform_name}%')
            ))
            platform_id = result.scalars().first()
            result = await db.execute(select(models.PlatformRepo.c.repository_id).where(
                models.PlatformRepo.c.platform_id == platform_id
            ))
            all_repo_ids = result.scalars().all()
            result = await db.execute(select(models.Repository.id).where(
                models.Repository.id.in_(all_repo_ids)
            ).where(
                models.Repository.production == True
            ))
            repo_ids.extend(result.scalars().all())
    return await fs_export_repository(db=db, repository_ids=repo_ids)


def main():
    args = parse_args()
    logger = logging.getLogger('packages-exporter')
    if args.verbose:
        logging.basicConfig(level=logging.DEBUG)
    else:
        logging.basicConfig(level=logging.INFO)
    platform_name = args.platform_name
    exported_paths = sync(export_repos_from_pulp(platform_name))
    logger.info('args=%s, platform_name=%s, exp_paths=%s',
                args, args.platform_name, exported_paths)
    
    createrepo_c = local['createrepo_c']
    modifyrepo_c = local['modifyrepo_c']
    for exp_path in exported_paths:
        path = Path(exp_path)
        repo_path = path.parent
        repodata = repo_path / 'repodata'
        modules_yaml = repodata / 'modules.yaml'
        if modules_yaml.exists():
            modifyrepo_c(modules_yaml, repodata)
        repomd_signer(repodata)


if __name__ == '__main__':
    main()

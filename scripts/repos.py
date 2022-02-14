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


def parse_args():
    parser = argparse.ArgumentParser(
        'packages_exporter',
        description='Packages exporter script. Exports repositories from Pulp'
                    'and transfer them to production host'
    )
    parser.add_argument('builds_ids', type=int, nargs='+')
    parser.add_argument('-v', '--verbose', action='store_true', default=False,
                        required=False, help='Enable verbose output')
    return parser.parse_args()


async def export_repos_from_pulp(builds_ids: typing.List[int]):
    async with database.Session() as db:
        repo_ids = []
        for build_id in builds_ids:
            result = await db.execute(select(models.Repository.id).join(
                models.BuildRepo, models.Repository.id ==
                models.BuildRepo.c.repository_id).where(
                    models.BuildRepo.c.build_id == build_id
                ).where(
                    models.Repository.production == True
                ))
            result_ids = result.scalars().all()
            repo_ids.extend(result_ids)
    return await fs_export_repository(db=db, repository_ids=repo_ids)


def main():
    args = parse_args()
    logger = logging.getLogger('packages-exporter')
    if args.verbose:
        logging.basicConfig(level=logging.DEBUG)
    else:
        logging.basicConfig(level=logging.INFO)
    builds_ids = args.builds_ids
    exported_paths = sync(export_repos_from_pulp(builds_ids))
    logger.info('args=%s, builds_ids=%s, exp_paths=%s',
                args, args.builds_ids, exported_paths)
    
    createrepo_c = local['createrepo_c']
    modifyrepo_c = local['modifyrepo_c']
    for exp_path in exported_paths:
        path = Path(exp_path)
        repo_path = path.parent
        repodata = repo_path / 'repodata'
        modules_yaml = repodata / 'modules.yaml'
        if modules_yaml.exists():
            modifyrepo_c(modules_yaml, repodata)


if __name__ == '__main__':
    main()

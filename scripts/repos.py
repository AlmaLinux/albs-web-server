import os
import sys
import typing
import argparse
import logging
import jmespath

from syncer import sync
from pathlib import Path
from plumbum import local
from sqlalchemy.future import select
from sqlalchemy.orm import selectinload

sys.path.append(os.path.dirname(os.path.dirname(__file__)))


from alws import database
from alws import models
from alws.config import settings
from alws.utils.pulp_client import PulpClient
from alws.utils.exporter import fs_export_repository
from repomd_signer import get_sign_keys_from_db, repomd_signer


def parse_args():
    parser = argparse.ArgumentParser(
        'packages_exporter',
        description='Packages exporter script. Exports repositories from Pulp'
                    'and transfer them to production host'
    )
    parser.add_argument('-names', '--platform_names',
                        type=str, nargs='+', required=False,
                        help='List of platform names to export')
    parser.add_argument('-a', '--arches', type=str, nargs='+',
                        required=False, help='List of arches to export')
    parser.add_argument('-id', '--release_id', type=int,
                        required=False, help='Extract repos by release_id')
    parser.add_argument('-v', '--verbose', action='store_true', default=False,
                        required=False, help='Enable verbose output')
    return parser.parse_args()


async def export_repos_from_pulp(platform_names: typing.List[str],
                                 platforms_dict: dict,
                                 arches: typing.List[str] = None):
    repo_ids = []
    async with database.Session() as db:
        db_platforms = await db.execute(
            select(models.Platform).where(
                models.Platform.name.in_(platform_names)).options(
                    selectinload(models.Platform.repos))
        )
    db_platforms = db_platforms.scalars().all()
    for db_platform in db_platforms:
        platforms_dict[db_platform.id] = []
        for repo in db_platform.repos:
            if repo.production is True:
                if arches is not None:
                    if repo.arch in arches:
                        platforms_dict[db_platform.id].append(repo.export_path)
                        repo_ids.append(repo.id)
                else:
                    platforms_dict[db_platform.id].append(repo.export_path)
                    repo_ids.append(repo.id)
    return await fs_export_repository(db=db, repository_ids=set(repo_ids))


async def export_repos_from_release_plan(release_id: int):
    repo_ids = []
    async with database.Session() as db:
        db_release = await db.execute(
            select(models.Release).where(models.Release.id == release_id))
    db_release = db_release.scalars().first()

    repo_ids = jmespath.search('packages[].repositories[].id',
                               db_release.plan)
    return (await fs_export_repository(db=db, repository_ids=set(repo_ids)),
            db_release.platform_id)


async def delete_existing_exporters_from_pulp():
    deleted_exporters = []
    pulp_client = PulpClient(
        settings.pulp_host,
        settings.pulp_user,
        settings.pulp_password,
    )
    existing_exporters = await pulp_client.list_filesystem_exporters()
    for exporter in existing_exporters:
        await pulp_client.delete_filesystem_exporter(exporter['pulp_href'])
        deleted_exporters.append(exporter['name'])
    return deleted_exporters


def main():
    args = parse_args()
    logger = logging.getLogger('packages-exporter')
    if args.verbose:
        logging.basicConfig(level=logging.DEBUG)
    else:
        logging.basicConfig(level=logging.INFO)

    platforms_dict = {}
    key_id_by_platform = None
    exported_paths = []

    deleted_exporters = sync(delete_existing_exporters_from_pulp())
    if deleted_exporters:
        logger.info('Following exporters, has been deleted from pulp:\n%s',
                    '\n'.join(str(i) for i in deleted_exporters))

    db_sign_keys = sync(get_sign_keys_from_db())

    if args.release_id:
        release_id = args.release_id
        logger.info('Start exporting packages from release id=%s',
                    release_id)
        exported_paths, platform_id = sync(
            export_repos_from_release_plan(release_id))
        key_id_by_platform = next((
            sign_key.keyid for sign_key in db_sign_keys
            if sign_key.platform_id == platform_id
        ), None)

    if args.platform_names:
        logger.info('Start exporting packages for following platforms:\n%s',
                    args.platform_names)
        exported_paths = sync(export_repos_from_pulp(
            args.platform_names, platforms_dict, args.arches))

    logger.info('All repositories exported in following paths:\n%s',
                '\n'.join((str(path) for path in exported_paths)))

    createrepo_c = local['createrepo_c']
    modifyrepo_c = local['modifyrepo_c']
    for exp_path in exported_paths:
        path = Path(exp_path)
        repo_path = path.parent
        repodata = repo_path / 'repodata'
        modules_yaml = repodata / 'modules.yaml'
        createrepo_c(repo_path)
        if modules_yaml.exists():
            modifyrepo_c(modules_yaml, repodata)
        key_id = key_id_by_platform or None
        for platform_id, platform_repos in platforms_dict.items():
            for repo_export_path in platform_repos:
                if repo_export_path in str(exp_path):
                    key_id = next((
                        sign_key.keyid for sign_key in db_sign_keys
                        if sign_key.platform_id == platform_id
                    ), None)
                    break
        if key_id is None:
            logger.info('Cannot sign repomd.xml in %s, missing GPG key',
                        str(exp_path))
            continue
        repomd_signer(repodata, key_id)
        logger.info('repomd.xml in %s is signed', str(repodata))


if __name__ == '__main__':
    main()

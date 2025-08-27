import argparse
import asyncio
import copy
import logging
import os
import pprint
import subprocess
import sys
import tempfile

from fastapi_sqla import open_async_session
from immudb_wrapper import ImmudbWrapper
from sqlalchemy import select
from sqlalchemy.orm import selectinload

sys.path.append(os.path.dirname(os.path.dirname(__file__)))

from alws import models
from alws.dependencies import get_async_db_key
from alws.utils.fastapi_sqla_setup import setup_all
from alws.utils.pulp_client import PulpClient

logging.basicConfig(
    format="%(asctime)s %(levelname)-8s %(message)s",
    level=logging.INFO,
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[
        logging.StreamHandler(),
    ],
)


def parse_args():
    parser = argparse.ArgumentParser(
        "build-notarizer",
        description="Creates records in immudb for the further usage in generating SBOM data",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        '--build-id',
        type=int,
        help='Build ID to process',
        required=True,
    )
    parser.add_argument(
        '--pulp-host',
        type=str,
        help='Pulp host',
        required=True,
    )
    parser.add_argument(
        '--pulp-username',
        type=str,
        help='Pulp username',
        required=True,
    )
    parser.add_argument(
        '--pulp-password',
        type=str,
        help='Pulp password',
        required=True,
    )
    parser.add_argument(
        '--immudb-address',
        type=str,
        help='Immudb address',
        required=True,
    )
    parser.add_argument(
        '--immudb-username',
        type=str,
        help='Immudb username',
        required=True,
    )
    parser.add_argument(
        '--immudb-password',
        type=str,
        help='Immudb password',
        required=True,
    )
    parser.add_argument(
        '--immudb-database',
        type=str,
        help='Immudb database',
        required=True,
    )
    return parser.parse_args()


def extract_git_metadata(
    task: models.BuildTask,
    immudb_wrapper: ImmudbWrapper,
) -> dict:
    metadata = {
        'source_type': 'git',
        'git_url': task.ref.url,
        'git_ref': task.ref.git_ref,
        'git_commit': task.ref.git_commit_hash,
    }
    if not task.ref.git_commit_hash:
        return metadata
    with tempfile.TemporaryDirectory() as tmpdir:
        subprocess.run(
            args=('git', 'clone', task.ref.url, '.'),
            cwd=tmpdir,
            check=True,
            capture_output=True,
            encoding='utf-8',
        )
        subprocess.run(
            args=('git', 'checkout', task.ref.git_commit_hash),
            cwd=tmpdir,
            check=True,
            capture_output=True,
            encoding='utf-8',
        )
        result = immudb_wrapper.authenticate_git_repo(tmpdir)
        if result:
            metadata['alma_commit_sbom_hash'] = (
                result.get('value', {})
                .get('Metadata', {})
                .get('git', {})
                .get('Commit')
            )
    return metadata


async def main(
    need_to_re_notarize: bool = False,
):
    args = parse_args()
    pulp_client = PulpClient(
        host=args.pulp_host,
        username=args.pulp_username,
        password=args.pulp_password,
    )
    immudb_wrapper = ImmudbWrapper(
        username=args.immudb_username,
        password=args.immudb_password,
        database=args.immudb_database,
        immudb_address=args.immudb_address,
    )
    await setup_all()
    async with open_async_session(get_async_db_key()) as session:
        build = await session.execute(
            select(models.Build)
            .where(models.Build.id == args.build_id)
            .options(
                selectinload(models.Build.owner),
                selectinload(models.Build.tasks).options(
                    selectinload(models.BuildTask.artifacts),
                    selectinload(models.BuildTask.ref),
                ),
            ),
        )
        build = build.scalars().first()
        for task in build.tasks:
            cas_metadata = {
                'build_id': task.build_id,
                'build_arch': task.arch,
                'built_by': f'{build.owner.username} <{build.owner.email}>',
                'sbom_api_ver': '0.2',
            }
            if task.ref.git_ref:
                cas_metadata.update(
                    **extract_git_metadata(task, immudb_wrapper),
                )
            # TODO: implement that later
            else:
                logging.warning(
                    'notarizing for projects from SRPMs is not implemented yet, skipping'
                )
                continue
            for artifact in task.artifacts:
                if (
                    artifact.type != 'rpm'
                    or artifact.cas_hash
                    and not need_to_re_notarize
                ):
                    continue
                try:
                    artifact_info = await pulp_client.get_artifact(
                        artifact.href,
                        exclude_fields=['changelogs'],
                    )
                except Exception:
                    # TODO: we probably should actualize pulp_hrefs in such cases
                    logging.warning(
                        'cannot get pkg %s info, skipping', artifact.name
                    )
                    continue
                if not artifact_info:
                    raise ValueError('Cannot get artifact info')
                metadata = {
                    'Name': artifact_info['location_href'],
                    'Kind': 'file',
                    'Size': immudb_wrapper.get_size_format(
                        artifact_info['size_package'],
                    ),
                    'Hash': artifact_info['sha256'],
                    'Signer': immudb_wrapper.username,
                    'Metadata': {
                        **copy.deepcopy(cas_metadata),
                        'build_host': artifact_info['rpm_buildhost'],
                        'name': artifact_info['name'],
                        'epoch': artifact_info['epoch'],
                        'version': artifact_info['version'],
                        'release': artifact_info['release'],
                        'arch': artifact_info['arch'],
                        'sourcerpm': (
                            None
                            if artifact_info['arch'] == 'src'
                            else artifact_info['rpm_sourcerpm']
                        ),
                    },
                }
                logging.debug('immudb payload:\n%s', pprint.pformat(metadata))
                immudb_wrapper.notarize(metadata['Hash'], metadata)
                artifact.cas_hash = metadata['Hash']
                logging.info('artifact %s processed', artifact.name)
        await session.commit()


asyncio.run(main())

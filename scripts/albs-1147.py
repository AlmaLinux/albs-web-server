import argparse
import asyncio
import datetime
import difflib
import logging
import os
import sys

from fastapi_sqla import open_async_session, open_session
from sqlalchemy import distinct, not_, or_, select

from alws.config import settings
from alws.dependencies import get_async_db_key
from alws.utils import pulp_client
from alws.utils.errata import debrand_description_and_title

sys.path.append(os.path.dirname(os.path.dirname(__file__)))

from alws.models import ErrataRecord
from alws.pulp_models import (
    CoreRepositoryContent,
    UpdateRecord,
)
from alws.utils.fastapi_sqla_setup import setup_all

logging.basicConfig(
    format="%(message)s",
    level=logging.INFO,
    datefmt="%m-%d %H:%M:%S",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("albs-1147.log"),
    ],
)
log = logging.getLogger()


def log_differences(original: str, new: str):
    original_words = original.split()
    new_words = new.split()

    matcher = difflib.SequenceMatcher(None, original_words, new_words)

    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == 'replace':
            original_change = ' '.join(original_words[i1:i2])
            new_change = ' '.join(new_words[j1:j2])

            start_context = max(0, i1 - 3)
            end_context = min(len(original_words), i2 + 3)
            original_context = (
                ' '.join(original_words[start_context:i1])
                + ' 【'
                + original_change
                + '】 '
                + ' '.join(original_words[i2:end_context])
            )

            start_context = max(0, j1 - 3)
            end_context = min(len(new_words), j2 + 3)
            new_context = (
                ' '.join(new_words[start_context:j1])
                + ' 【'
                + new_change
                + '】 '
                + ' '.join(new_words[j2:end_context])
            )

            log.info(f'... {original_context} ➔ {new_context}')


async def main(write=False):
    ignore_parts = [
        'access.redhat.com',
        'container-tools:rhel8',
        'eclipse:rhel8',
        'go-toolset:rhel8',
        'jmc:rhel8',
        'llvm-toolset:rhel8',
        'rust-toolset:rhel8',
        'virt:rhel',
        'virt-devel:rhel',
        'ansible-collection-redhat-rhel_mgmt',
        'ansible-collection-AlmaLinux-rhel_mgmt',
        'rhel-system-roles',
        'lorax-templates-rhel',
        'redhat-rpm-config',
        'kmod-redhat-oracleasm',
        'rhel8 stream',
    ]
    search_parts = ['rhel', 'red hat', 'redhat']
    affected_records = {}
    affected_records_content_ids = []
    repos_to_publicate = set()
    pulp_client.PULP_SEMAPHORE = asyncio.Semaphore(10)
    pulp = pulp_client.PulpClient(
        settings.pulp_host, settings.pulp_user, settings.pulp_password
    )
    await setup_all()

    with open_session(key="pulp") as session:
        result = session.execute(
            select(UpdateRecord).where(
                or_(
                    *[
                        UpdateRecord.description.ilike(f'%{part}%')
                        for part in search_parts
                    ],
                    *[
                        UpdateRecord.title.ilike(f'%{part}%')
                        for part in search_parts
                    ],
                ),
                not_(
                    or_(
                        *[
                            UpdateRecord.description.ilike(f'%{part}%')
                            for part in ignore_parts
                        ],
                        *[
                            UpdateRecord.title.ilike(f'%{part}%')
                            for part in ignore_parts
                        ],
                    )
                ),
            )
        )
        records = result.scalars().all()

        log.info(
            f'Found {len(records)} records in Pulp\'s \'rpm_updaterecord\' table.'
        )
        for record in records:
            log.info(f'{record.id} - {record.title}')
            debranded_title = debrand_description_and_title(record.title)
            debranded_description = debrand_description_and_title(
                record.description
            )
            log_differences(record.title, debranded_title)
            log_differences(record.description, debranded_description)
            record.title = debranded_title
            record.description = debranded_description
            record.updated_date = datetime.datetime.utcnow().strftime(
                "%Y-%m-%d %H:%M:%S",
            )
            affected_records[record.id] = {
                'title': record.title,
                'description': record.description,
                'content_ptr_id': record.content_ptr_id,
            }
            affected_records_content_ids.append(record.content_ptr_id)

        query = select(distinct(CoreRepositoryContent.repository_id)).where(
            CoreRepositoryContent.version_removed_id.is_(None),
            CoreRepositoryContent.content_id.in_(affected_records_content_ids),
        )
        repos = session.execute(query).scalars().all()
        for repo in repos:
            repo_href = f"/pulp/api/v3/repositories/rpm/rpm/{repo}/"
            repos_to_publicate.add(repo_href)

        if write:
            session.add_all(records)
            session.flush()
            publication_tasks = []
            for repo_href in repos_to_publicate:
                publication_tasks.append(pulp.create_rpm_publication(repo_href))
            log.info("Publishing updated repos. This may take a while")
            await asyncio.gather(*publication_tasks)

    log.info(
        f'{os.linesep * 2}Looking for records in almalinux\'s '
        f'\'errata_records\' table...'
    )

    async with open_async_session(get_async_db_key()) as session:
        result = await session.execute(
            select(ErrataRecord).where(
                ErrataRecord.id.in_(list(affected_records.keys()))
            )
        )
        records = result.scalars().all()
        log.info(f'Found {len(records)} records.')

        for record in records:
            log.info(f'{record.id} - {record.title or record.original_title}')
            log_differences(
                record.original_title, affected_records[record.id]['title']
            )
            log_differences(
                record.original_description,
                affected_records[record.id]['description'],
            )
            record.original_title = affected_records[record.id]['title']
            record.original_description = affected_records[record.id][
                'description'
            ]
            record.updated_date = datetime.datetime.utcnow()

        if write:
            session.add_all(records)
            await session.flush()


def confirm():
    confirmation = input(
        f"WARNING: Are you sure you want to write changes? {os.linesep}"
        "This may cause issues if you haven't run a dry check. (y/N): "
    )
    if confirmation.lower() != 'y':
        print("Write operation cancelled.")
        exit(1)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description='This script fixes errata branding issues from Pulp\'s perspective'
    )
    parser.add_argument(
        '--write', action='store_true', help='Allow write changes to database'
    )
    args = parser.parse_args()
    if args.write:
        confirm()

    asyncio.run(main(args.write))

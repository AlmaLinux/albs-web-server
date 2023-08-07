import difflib
import argparse
import re
import asyncio
import datetime
import logging
import os
import sys

from contextlib import asynccontextmanager

from sqlalchemy import select, or_, not_, and_

from alws.config import settings
from alws.dependencies import get_pulp_db, get_db
from alws.utils.pulp_client import PulpClient

sys.path.append(os.path.dirname(os.path.dirname(__file__)))

from alws.models import ErrataRecord
from alws.pulp_models import UpdateRecord, CoreRepository, CoreRepositoryContent, CoreContent

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


def debrand_description_and_title(original_string: str) -> str:
    branding_patterns = (
        (r'RHEL', 'AlmaLinux'),
        (r'\[rhel', '[almalinux'),
        (r'\(rhel', '(almalinux'),
        (r'connect to rhel server', 'connect to almalinux server'),
        (r'kvm-rhel8.3', 'kvm-almalinux8.3'),
        ('rhel-9', 'almalinux-9'),
        ('rhel-8', 'almalinux-8'),
        ('rhel9.2', 'almalinux9.2'),
        ('rhel-8.5', 'almalinux-8.5'),
        ('rhel 8.4', 'almalinux 8.4')
    )
    for pattern, repl in branding_patterns:
        original_string = re.sub(pattern, repl, original_string)
    return original_string


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
            original_context = ' '.join(original_words[start_context:i1]) \
                               + ' 【' + original_change + '】 ' \
                               + ' '.join(original_words[i2:end_context])

            start_context = max(0, j1 - 3)
            end_context = min(len(new_words), j2 + 3)
            new_context = ' '.join(new_words[start_context:j1]) \
                          + ' 【' + new_change + '】 ' \
                          + ' '.join(new_words[j2:end_context])

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
        'rhel8 stream'
    ]
    search_parts = [
        'rhel',
        'red hat',
        'redhat'
    ]
    affected_records = {}

    with get_pulp_db() as session:
        result = session.execute(
            select(UpdateRecord).where(
                or_(
                    *[UpdateRecord.description.ilike(f'%{part}%') for part in search_parts],
                    *[UpdateRecord.title.ilike(f'%{part}%') for part in search_parts],
                ),
                not_(
                    or_(
                        *[UpdateRecord.description.ilike(f'%{part}%') for part in ignore_parts],
                        *[UpdateRecord.title.ilike(f'%{part}%') for part in ignore_parts],
                    )
                )
            )
        )
        records = result.scalars().all()

        log.info(f'Found {len(records)} records in Pulp\'s \'rpm_updaterecord\' table.')
        for record in records:
            log.info(f'{record.id} - {record.title}')
            debranded_title = debrand_description_and_title(record.title)
            debranded_description = debrand_description_and_title(record.description)
            log_differences(record.title, debranded_title)
            log_differences(record.description, debranded_description)
            record.title = debranded_title
            record.description = debranded_description
            affected_records[record.id] = {
                'title': record.title,
                'description': record.description,
                'content_ptr_id': record.content_ptr_id
            }
            record.updated_date = datetime.datetime.utcnow().strftime(
                "%Y-%m-%d %H:%M:%S",
            )

        if write:
            session.commit()

    log.info(f'{os.linesep * 2}Looking for records in almalinux\'s \'errata_records\' table...')

    async with asynccontextmanager(get_db)() as session, session.begin():
        result = await session.execute(
            select(ErrataRecord).where(
                ErrataRecord.id.in_(list(affected_records.keys()))
            )
        )
        records = result.scalars().all()
        log.info(f'Found {len(records)} records.')

        for record in records:
            log.info(f'{record.id} - {record.title or record.original_title}')
            log_differences(record.original_title, affected_records[record.id]['title'])
            log_differences(record.original_description, affected_records[record.id]['description'])
            record.original_title = affected_records[record.id]['title']
            record.original_description = affected_records[record.id]['description']
            record.updated_date = datetime.datetime.utcnow()

        if write:
            await session.commit()

    repos_to_publicate = set()
    pulp = PulpClient(settings.pulp_host, settings.pulp_user, settings.pulp_password)

    with get_pulp_db() as pulp_db, pulp_db.begin():
        repos = pulp_db.execute(select(CoreRepository)).scalars().all()
        for repo in repos:
            repo_href = f"/pulp/api/v3/repositories/rpm/rpm/{repo.pulp_id}/"

            repo_subq = (
                select(CoreRepository.pulp_id).where(
                    CoreRepository.name == repo.name
                )
            )

            repocontent_subq = (
                select(CoreRepositoryContent.content_id).where(
                    CoreRepositoryContent.repository_id.in_(repo_subq)
                )
            )

            content_subq = (
                select(CoreContent.pulp_id).where(
                    CoreContent.pulp_type == 'rpm.advisory',
                    CoreContent.pulp_id.in_(repocontent_subq)
                )
            )

            updaterecord_subq = (
                select(UpdateRecord).where(
                    and_(
                        UpdateRecord.content_ptr_id.in_(content_subq),
                        UpdateRecord.content_ptr_id.in_(
                            {v['content_ptr_id'] for k, v in affected_records.items()})
                    )
                )
            )

            records = pulp_db.execute(updaterecord_subq).scalars().all()

            for record in records:
                log.info(f"Updating {record.id} from {repo.name}")
                if repo_href not in repos_to_publicate:
                    repos_to_publicate.add(repo_href)
    if write:
        publication_tasks = []
        for repo_href in repos_to_publicate:
            publication_tasks.append(pulp.create_rpm_publication(repo_href))
        log.info("Publicating updated repos. This may take a while")
        await asyncio.gather(*publication_tasks)


def confirm():
    confirmation = input(f"WARNING: Are you sure you want to write changes? {os.linesep}"
                         "This may cause issues if you haven't run a dry check. (y/N): ")
    if confirmation.lower() != 'y':
        print("Write operation cancelled.")
        exit(1)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='This script fixes errata branding issues from Pulp\'s perspective')
    parser.add_argument('--write', action='store_true', help='Allow write changes to database')
    args = parser.parse_args()
    if args.write:
        confirm()

    asyncio.run(main(args.write))

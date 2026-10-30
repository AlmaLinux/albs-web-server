"""Align advisory fields that differ only cosmetically across copies.

The same advisory ID is stored once per platform in ALBS
(new_errata_records) and once per repository in Pulp (rpm_updaterecord).
Records imported in different ways can end up with the same title or
description that only differs in whitespace, or the same severity in a
different case, which breaks consumers that merge advisories by ID only
when their fields are equal (e.g. OSV).

For every advisory ID the script collects all the variants of each field
from ALBS and Pulp. When the variants are equal after normalization, it
picks one canonical variant and writes it everywhere, then republishes the
affected Pulp repositories so updateinfo.xml gets fixed too. Differences
that are not cosmetic are reported and left untouched.

The canonical variant is, in order of preference:
  1. the one of the --source-platform record;
  2. the one shared by all the released copies, where a copy is released
     when its ALBS record is marked so or when its platform has the
     advisory published in Pulp;
  3. a fallback: the least whitespace for texts, lowercase for severity
     (this is what the current errata import produces).

ALBS records whose advisory is published in Pulp for their platform but
that are not marked as released (e.g. a later re-release attempt failed
because the packages are gone) are reported, pass --sync-release-status to
mark them as released.

Dry run by default, pass --apply to write the changes.

Examples:
    python scripts/fix_errata_text_discrepancies.py \
        --ids ALSA-2024:1822 ALSA-2024:1828
    python scripts/fix_errata_text_discrepancies.py --apply \
        --source-platform AlmaLinux-8 --sync-release-status \
        --ids ALSA-2024:1822 ALSA-2024:1828
    python scripts/fix_errata_text_discrepancies.py  # scan everything
"""

import argparse
import asyncio
import logging
import os
import sys
import typing
import uuid
from collections import Counter
from dataclasses import dataclass, field

from fastapi_sqla import open_async_session, open_session
from sqlalchemy import func, select
from sqlalchemy.orm import selectinload

sys.path.append(os.path.dirname(os.path.dirname(__file__)))

from alws import models
from alws.config import settings
from alws.constants import ErrataReleaseStatus
from alws.dependencies import get_async_db_key
from alws.pulp_models import (
    CoreRepository,
    CoreRepositoryContent,
    UpdateRecord,
)
from alws.utils.fastapi_sqla_setup import setup_all
from alws.utils.pulp_client import PulpClient

# Text fields present both in ALBS records and in Pulp advisories.
# In ALBS each of them can be overridden: <field> takes precedence over
# original_<field>, see NewErrataRecord.get_description/get_title.
TEXT_FIELDS = ('title', 'description')
# Severity is only compared in ALBS, the release always capitalizes it
# for Pulp (see crud.errata.release_errata_packages)
FIELDS = TEXT_FIELDS + ('severity',)
CHUNK_SIZE = 500


def parse_args():
    parser = argparse.ArgumentParser(
        'fix_errata_text_discrepancies',
        description=(
            'Align errata titles/descriptions/severities that differ only '
            'cosmetically across platforms in ALBS and Pulp'
        ),
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        '--ids',
        nargs='+',
        default=None,
        help='Advisory IDs to check, all advisories are scanned if omitted',
    )
    parser.add_argument(
        '--fields',
        nargs='+',
        choices=FIELDS,
        default=list(FIELDS),
        help='Fields to align',
    )
    parser.add_argument(
        '--source-platform',
        default=None,
        help=(
            'Take the canonical values from the record of this platform '
            '(e.g. AlmaLinux-8) instead of the released copies'
        ),
    )
    parser.add_argument(
        '--sync-release-status',
        action='store_true',
        default=False,
        help=(
            'Mark ALBS records as released when their advisory is '
            'published in Pulp for their platform'
        ),
    )
    parser.add_argument(
        '--apply',
        action='store_true',
        default=False,
        help='Write changes to the databases and republish repositories',
    )
    parser.add_argument(
        '--no-publish',
        action='store_true',
        default=False,
        help='Do not republish affected Pulp repositories',
    )
    return parser.parse_args()


def normalize(field_name: str, value: typing.Optional[str]) -> str:
    if field_name == 'severity':
        return (value or '').lower()
    return ' '.join((value or '').split())


def fallback_key(field_name: str, variant: str):
    if field_name == 'severity':
        # the current errata import stores severities in lowercase
        return variant != variant.lower()
    # the broken variants are usually the ones with extra whitespace
    return len(variant)


def pick_canonical(
    field_name: str,
    variants: typing.Iterable[str],
    released: typing.Iterable[str] = (),
    preferred: typing.Optional[str] = None,
) -> typing.Tuple[typing.Optional[str], str]:
    """Pick the variant every other one should be replaced with.

    Returns the variant and the reason it was picked. The variant is None
    when the variants differ not only cosmetically, such records must be
    checked and fixed manually.
    """
    counts = Counter(variants)
    if len({normalize(field_name, variant) for variant in counts}) > 1:
        return None, 'differs not only cosmetically'
    if preferred is not None and preferred in counts:
        return preferred, 'source platform'
    released = set(released)
    if len(released) == 1:
        return released.pop(), 'released copies'
    reason = 'fallback'
    if released:
        reason = 'fallback, released copies differ'
    return (
        min(
            counts,
            key=lambda variant: (
                fallback_key(field_name, variant),
                -counts[variant],
            ),
        ),
        reason,
    )


@dataclass
class FieldFix:
    record_id: str
    field: str
    canonical: str
    reason: str
    # variant -> labels of the copies that hold it
    sources: typing.Dict[str, typing.List[str]]
    albs_records: typing.List[models.NewErrataRecord] = field(
        default_factory=list
    )
    pulp_records: typing.List[UpdateRecord] = field(default_factory=list)


def get_albs_value(record: models.NewErrataRecord, field_name: str) -> str:
    if field_name not in TEXT_FIELDS:
        return getattr(record, field_name)
    return getattr(record, field_name) or getattr(
        record, f'original_{field_name}'
    )


def set_albs_value(
    record: models.NewErrataRecord,
    field_name: str,
    value: str,
):
    if field_name not in TEXT_FIELDS:
        setattr(record, field_name, value)
        return
    # Same approach as in crud.errata.update_errata_record: keep the
    # override empty when it matches the original text
    if value == getattr(record, f'original_{field_name}'):
        value = None
    setattr(record, field_name, value)


def get_pulp_platform(
    record: UpdateRecord,
    platform_names: typing.Iterable[str],
) -> typing.Optional[str]:
    # Collections are named <platform>-for-<arch>-<repo>-rpms__<version>,
    # see crud.errata.release_errata_packages
    for collection in record.collections:
        for platform_name in platform_names:
            if collection.name.startswith(f'{platform_name.lower()}-for-'):
                return platform_name
    return None


def get_published_platforms(
    albs_records: typing.List[models.NewErrataRecord],
    pulp_records: typing.List[UpdateRecord],
) -> typing.Dict[uuid.UUID, typing.Optional[str]]:
    platform_names = [record.platform.name for record in albs_records]
    return {
        record.content_ptr_id: get_pulp_platform(record, platform_names)
        for record in pulp_records
    }


def is_released(
    record: models.NewErrataRecord,
    published_platforms: typing.Iterable[typing.Optional[str]],
) -> bool:
    return (
        record.release_status == ErrataReleaseStatus.RELEASED
        or record.platform.name in published_platforms
    )


def plan_status_fixes(
    albs_records: typing.List[models.NewErrataRecord],
    published_platforms: typing.Iterable[typing.Optional[str]],
) -> typing.List[models.NewErrataRecord]:
    published_platforms = set(published_platforms)
    return [
        record
        for record in albs_records
        if record.release_status != ErrataReleaseStatus.RELEASED
        and record.platform.name in published_platforms
    ]


def describe_sources(
    field_name: str,
    albs_records: typing.List[models.NewErrataRecord],
    pulp_records: typing.List[UpdateRecord],
    published_platforms: typing.Dict[uuid.UUID, typing.Optional[str]],
) -> typing.Dict[str, typing.List[str]]:
    sources = {}
    for record in albs_records:
        sources.setdefault(get_albs_value(record, field_name), []).append(
            f'ALBS {record.platform.name} ({record.release_status.value})'
        )
    pulp_counts = Counter(
        (
            getattr(record, field_name) or '',
            published_platforms.get(record.content_ptr_id) or 'unknown',
        )
        for record in pulp_records
    )
    for (variant, platform_name), count in sorted(pulp_counts.items()):
        sources.setdefault(variant, []).append(f'Pulp {platform_name} x{count}')
    return sources


def plan_fixes(
    record_id: str,
    albs_records: typing.List[models.NewErrataRecord],
    pulp_records: typing.List[UpdateRecord],
    fields: typing.Iterable[str],
    source_platform: typing.Optional[str] = None,
) -> typing.Tuple[typing.List[FieldFix], typing.List[str]]:
    published_platforms = get_published_platforms(albs_records, pulp_records)
    fixes = []
    problems = []
    for field_name in fields:
        field_pulp_records = pulp_records
        if field_name not in TEXT_FIELDS:
            field_pulp_records = []
        albs_values = {
            record.platform.name: get_albs_value(record, field_name)
            for record in albs_records
        }
        variants = list(albs_values.values()) + [
            getattr(record, field_name) or '' for record in field_pulp_records
        ]
        if len(set(variants)) < 2:
            continue
        released = [
            get_albs_value(record, field_name)
            for record in albs_records
            if is_released(record, published_platforms.values())
        ]
        canonical, reason = pick_canonical(
            field_name,
            variants,
            released=released,
            preferred=albs_values.get(source_platform),
        )
        if canonical is None:
            problems.append(f'{record_id}: {field_name} {reason}, skipping')
            continue
        fix = FieldFix(
            record_id=record_id,
            field=field_name,
            canonical=canonical,
            reason=reason,
            sources=describe_sources(
                field_name,
                albs_records,
                field_pulp_records,
                published_platforms,
            ),
            albs_records=[
                record
                for record in albs_records
                if get_albs_value(record, field_name) != canonical
            ],
            pulp_records=[
                record
                for record in field_pulp_records
                if getattr(record, field_name) != canonical
            ],
        )
        fixes.append(fix)
    return fixes, problems


async def find_candidate_ids(
    albs_db,
    pulp_db,
    fields: typing.Iterable[str],
) -> typing.List[str]:
    # Only advisories with several copies can have discrepancies:
    # released for several platforms in ALBS or present in several
    # repositories in Pulp
    albs_ids = (
        (
            await albs_db.execute(
                select(models.NewErrataRecord.id)
                .group_by(models.NewErrataRecord.id)
                .having(func.count() > 1)
            )
        )
        .scalars()
        .all()
    )
    pulp_fields = [
        field_name for field_name in fields if field_name in TEXT_FIELDS
    ]
    pulp_ids = []
    if pulp_fields:
        pulp_ids = (
            pulp_db.execute(
                select(UpdateRecord.id)
                .group_by(UpdateRecord.id)
                .having(
                    func.greatest(*(
                        func.count(getattr(UpdateRecord, field_name).distinct())
                        for field_name in pulp_fields
                    ))
                    > 1
                )
            )
            .scalars()
            .all()
        )
    return sorted(set(albs_ids) | set(pulp_ids))


def get_repos(
    pulp_db,
    content_ids: typing.Iterable[uuid.UUID],
) -> typing.Dict[str, typing.Tuple[str, bool]]:
    """Return {repo_href: (repo_name, user_hidden)} of repos with the content.

    Hidden repos are sub-repositories pulp_rpm creates when syncing a tree
    with .treeinfo, they're not exposed in the API and can't be published
    on their own.
    """
    repos = pulp_db.execute(
        select(
            CoreRepository.pulp_id,
            CoreRepository.name,
            CoreRepository.user_hidden,
        )
        .join(
            CoreRepositoryContent,
            CoreRepositoryContent.repository_id == CoreRepository.pulp_id,
        )
        .where(
            CoreRepositoryContent.content_id.in_(list(content_ids)),
            CoreRepositoryContent.version_removed_id.is_(None),
        )
        .distinct()
    ).all()
    return {
        f'/pulp/api/v3/repositories/rpm/rpm/{repo_id}/': (name, hidden)
        for repo_id, name, hidden in repos
    }


async def process_chunk(
    albs_db,
    pulp_db,
    record_ids: typing.List[str],
    args,
) -> typing.Tuple[
    typing.List[FieldFix],
    typing.List[models.NewErrataRecord],
    typing.List[str],
]:
    albs_records = (
        (
            await albs_db.execute(
                select(models.NewErrataRecord)
                .where(models.NewErrataRecord.id.in_(record_ids))
                .options(selectinload(models.NewErrataRecord.platform))
            )
        )
        .scalars()
        .all()
    )
    pulp_records = (
        pulp_db.execute(
            select(UpdateRecord)
            .where(UpdateRecord.id.in_(record_ids))
            .options(selectinload(UpdateRecord.collections))
        )
        .scalars()
        .all()
    )
    albs_by_id = {}
    for record in albs_records:
        albs_by_id.setdefault(record.id, []).append(record)
    pulp_by_id = {}
    for record in pulp_records:
        pulp_by_id.setdefault(record.id, []).append(record)

    fixes = []
    status_fixes = []
    problems = []
    for record_id in record_ids:
        record_albs = albs_by_id.get(record_id, [])
        record_pulp = pulp_by_id.get(record_id, [])
        record_fixes, record_problems = plan_fixes(
            record_id,
            record_albs,
            record_pulp,
            args.fields,
            source_platform=args.source_platform,
        )
        fixes.extend(record_fixes)
        problems.extend(record_problems)
        status_fixes.extend(
            plan_status_fixes(
                record_albs,
                get_published_platforms(record_albs, record_pulp).values(),
            )
        )
    return fixes, status_fixes, problems


def log_fix(fix: FieldFix):
    logging.info(
        '%s: %s will be set to %r (%s)',
        fix.record_id,
        fix.field,
        fix.canonical,
        fix.reason,
    )
    for variant, labels in fix.sources.items():
        marker = '=' if variant == fix.canonical else '!'
        logging.info('  %s %s: %r', marker, ', '.join(labels), variant)


def apply_fix(fix: FieldFix):
    for record in fix.albs_records:
        set_albs_value(record, fix.field, fix.canonical)
    for record in fix.pulp_records:
        setattr(record, fix.field, fix.canonical)


async def main():
    args = parse_args()
    logging.basicConfig(
        format="%(asctime)s %(levelname)-8s %(message)s",
        level=logging.INFO,
        datefmt="%Y-%m-%d %H:%M:%S",
        handlers=[
            logging.StreamHandler(),
            logging.FileHandler('fix_errata_text_discrepancies.log'),
        ],
    )
    await setup_all()
    repos_to_publish = {}
    total_fixes = 0
    total_status_fixes = 0
    all_problems = []
    async with open_async_session(key=get_async_db_key()) as albs_db:
        with open_session(key='pulp') as pulp_db:
            record_ids = args.ids or await find_candidate_ids(
                albs_db, pulp_db, args.fields
            )
            logging.info('Checking %d advisories', len(record_ids))
            for start in range(0, len(record_ids), CHUNK_SIZE):
                chunk = record_ids[start : start + CHUNK_SIZE]
                fixes, status_fixes, problems = await process_chunk(
                    albs_db, pulp_db, chunk, args
                )
                all_problems.extend(problems)
                for record in status_fixes:
                    logging.info(
                        '%s: %s is published in Pulp but marked as %s',
                        record.id,
                        record.platform.name,
                        record.release_status.value,
                    )
                    total_status_fixes += 1
                    if args.apply and args.sync_release_status:
                        record.release_status = ErrataReleaseStatus.RELEASED
                for fix in fixes:
                    log_fix(fix)
                    total_fixes += 1
                    repos_to_publish.update(
                        get_repos(
                            pulp_db,
                            (r.content_ptr_id for r in fix.pulp_records),
                        )
                    )
                    if args.apply:
                        apply_fix(fix)
            if not args.apply:
                # nothing was changed, but don't let the context managers
                # commit anything just in case
                await albs_db.rollback()
                pulp_db.rollback()
    for problem in all_problems:
        logging.warning(problem)
    logging.info(
        'Found %d field(s) to align, %d field(s) need manual check, '
        '%d record(s) published but not marked as released',
        total_fixes,
        len(all_problems),
        total_status_fixes,
    )
    if total_status_fixes and not args.sync_release_status:
        logging.info('Use --sync-release-status to mark them as released')
    hidden_repos = {
        href: name
        for href, (name, hidden) in repos_to_publish.items()
        if hidden
    }
    repos_to_publish = {
        href: name
        for href, (name, hidden) in repos_to_publish.items()
        if not hidden
    }
    logging.info('Repositories to republish: %d', len(repos_to_publish))
    for repo_href, repo_name in sorted(
        repos_to_publish.items(), key=lambda item: item[1]
    ):
        logging.info('  %s %s', repo_name, repo_href)
    if hidden_repos:
        logging.info(
            'Skipping %d hidden sub-repositories, they are republished '
            'with their parent repository:',
            len(hidden_repos),
        )
        for repo_href, repo_name in sorted(
            hidden_repos.items(), key=lambda item: item[1]
        ):
            logging.info('  %s %s', repo_name, repo_href)
    if not args.apply:
        logging.info('Dry run, nothing was changed. Use --apply to fix')
        return
    if args.no_publish or not repos_to_publish:
        return
    pulp = PulpClient(
        settings.pulp_host,
        settings.pulp_user,
        settings.pulp_password,
    )
    logging.info('Republishing %d repositories', len(repos_to_publish))
    repo_hrefs = sorted(repos_to_publish)
    results = await asyncio.gather(
        *(
            pulp.create_rpm_publication(repo_href, sleep_time=30.0)
            for repo_href in repo_hrefs
        ),
        return_exceptions=True,
    )
    failed = 0
    for repo_href, result in zip(repo_hrefs, results):
        if isinstance(result, BaseException):
            failed += 1
            logging.error(
                'Cannot republish %s %s: %r',
                repos_to_publish[repo_href],
                repo_href,
                result,
            )
    logging.info(
        'Republished %d of %d repositories',
        len(repo_hrefs) - failed,
        len(repo_hrefs),
    )


if __name__ == '__main__':
    asyncio.run(main())

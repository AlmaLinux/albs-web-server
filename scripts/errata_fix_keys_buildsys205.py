#!/bin/env python

"""
Setting correct gpg key_id for AlmaLinux-8 errata record
Context: https://github.com/AlmaLinux/build-system/issues/205
"""

import argparse
import asyncio
import json
import logging
import os
import sys
from contextlib import asynccontextmanager
from copy import deepcopy
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional

from pydantic import BaseModel
from sqlalchemy import and_, asc, desc, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

# fmt: off
sys.path.append(str(Path(__file__).parent.parent))
from alws import models
from alws.dependencies import get_db
# fmt: on


# New key after Jan 15 2024
AL8_GPG_KEY_UPDATE_DATE = datetime(2024, 1, 15)
AL8_NEW_KEY_GPG_ID = '2ae81e8aced7258b'
AL8_OLD_KEY_GPG_ID = '51d6647ec21ad6ea'
AL8_NAME = 'AlmaLinux-8'


class FixAlma8ErrataKeys:
    """Fix AlmaLinux 8 Errata Keys"""

    def __init__(
        self,
        dry_run: bool,
        db: AsyncSession,
        backup_dir: Optional[Path] = None,
        backup_before_update: bool = False,
    ):
        """
        Initialize FixAlma8ErrataKeys instance.

        Args:
            dry_run (bool): Flag indicating whether to perform a dry run.
            db (AsyncSession): Asynchronous database session.
            backup_dir (Optional[Path], optional):
                Directory to store backups. Defaults to None.
            backup_before_update (bool, optional):
                Flag indicating whether to backup before updating.
                Defaults to False.
        """
        self.db = db
        self.dry_run = dry_run
        self.backup_dir = backup_dir
        self.backup_before_update = backup_before_update

    async def get_alma8_platform_id(self) -> int:
        """
        Retrieve the platform ID for AlmaLinux 8.

        Returns:
            int: Platform ID.
        """
        stmt = select(models.Platform.id).where(
            models.Platform.name == AL8_NAME
        )
        platform_id = await self.db.scalar(stmt)
        if not platform_id:
            raise ValueError(f'Cant find platform_id for {AL8_NAME}')
        return platform_id

    async def get_errata_record(
        self, errata_record_id: str
    ) -> Optional[models.NewErrataRecord]:
        """
        Retrieve an errata record by its ID.

        Args:
            errata_record_id (str): Errata record ID.

        Returns:
            Optional[models.NewErrataRecord]:
                Errata record if found, else None.
        """
        platform_id = await self.get_alma8_platform_id()
        query = (
            select(models.NewErrataRecord)
            .options(
                selectinload(models.NewErrataRecord.packages)
                .selectinload(models.NewErrataPackage.albs_packages)
                .selectinload(models.NewErrataToALBSPackage.build_artifact)
                .selectinload(models.BuildTaskArtifact.build_task)
            )
            .where(
                and_(
                    models.NewErrataRecord.platform_id == platform_id,
                    models.NewErrataRecord.id == errata_record_id,
                )
            )
        )
        errata_record = await self.db.scalar(query)
        return errata_record

    async def get_errata_record_build_id(
        self, errata_record: models.NewErrataRecord
    ) -> Optional[str]:
        """
        Retrieve the build ID associated with an errata record.

        Args:
            errata_record (models.NewErrataRecord): Errata record.

        Returns:
            Optional[str]: Build ID if found, else None.
        """
        build_id = None
        for package in errata_record.packages:
            if not package.albs_packages:
                continue
            build_id = package.albs_packages[0].build_id
            break
        return build_id

    async def get_latest_sign_task_ts(
        self, build_id: str
    ) -> Optional[datetime]:
        """
        Retrieve the timestamp of the latest sign task
        associated with a build ID.

        Args:
            build_id (str): Build ID.

        Returns:
            Optional[datetime]: Timestamp if found, else None.
        """
        select_sign_task_ts_stmt = (
            select(models.SignTask.ts)
            .where(
                and_(
                    models.SignTask.build_id == build_id,
                    models.SignTask.ts.isnot(None),
                )
            )
            .order_by(desc(models.SignTask.id))
            .limit(1)
        )
        newest_ts = await self.db.scalar(select_sign_task_ts_stmt)
        return newest_ts

    def backup_state(self, errata_record_id: str, state: List[Dict[str, Any]]):
        """
        Backup the state of an errata record.

        Args:
            errata_record_id (str): Errata record ID.
            state (List[Dict[str, Any]]): State to be backed up.
        """
        backup_file_path = self.backup_dir / f'{errata_record_id}.json'
        with open(backup_file_path, 'w', encoding='utf-8') as fle:
            json.dump(state, fle, indent=2)

    async def get_expected_key_id(
        self, errata_record_id: str
    ) -> Optional[str]:
        """
        Retrieve the expected GPG key ID for an errata record.

        Args:
            errata_record_id (str): Errata record ID.

        Returns:
            Optional[str]: Expected GPG key ID if found, else None.
        """
        build_id = await self.get_errata_record_build_id(errata_record_id)
        if not build_id:
            logging.error('Cant extract build_id from %s', errata_record_id)
            return None
        newest_sign_task_ts = await self.get_latest_sign_task_ts(build_id)
        if not newest_sign_task_ts:
            logging.error(
                'Cant get timestamp of the latest sign task for build %s',
                build_id,
            )
            return None

        if newest_sign_task_ts < AL8_GPG_KEY_UPDATE_DATE:
            return AL8_OLD_KEY_GPG_ID
        return AL8_NEW_KEY_GPG_ID

    async def update_state(
        self, expected_key_id: str, errata_record: models.NewErrataRecord
    ):
        """
        Update the state of an errata record.

        Args:
            expected_key_id (str): Expected GPG key ID.
            errata_record (models.NewErrataRecord): Errata record.
        """
        new_states = []
        update_needed = False
        for state in errata_record.original_states:
            new_state = deepcopy(state)
            if (
                'signature_keyid' in new_state
                and new_state['signature_keyid'] is not None
                and new_state['signature_keyid'] != expected_key_id
            ):
                new_state['signature_keyid'] = expected_key_id
                update_needed = True
            new_states.append(new_state)

        if update_needed:
            assert len(errata_record.original_states) == len(new_states)
            if self.backup_before_update:
                backup_record = {
                    'original': errata_record.original_states,
                    'updated': new_states,
                }
                self.backup_state(errata_record.id, backup_record)
            if not self.dry_run:
                logging.info(
                    'Updating original_states for %s', errata_record.id
                )
                errata_record.original_states = new_states
                await self.db.commit()

    async def restore_state(self, errata_record_id: str, backup_file: Path):
        """
        Restore the state of an errata record from a backup.

        Args:
            errata_record_id (str): Errata record ID.
            backup_file (Path): Path to the backup file.
        """
        errata_record = await self.get_errata_record(errata_record_id)
        if not errata_record:
            logging.info(
                'Errata record %s does not exist in db', errata_record_id
            )
            return
        try:
            with open(backup_file, 'r') as fle:
                backuped_state = json.load(fle)['original']
        except Exception as e:  # pylint: disable=W0718
            logging.error('Cant load state %s: %s', backup_file, str(e))
            return
        if errata_record.original_states == backuped_state:
            logging.info(
                'Data in db already matches the backup. No need to update'
            )
            return
        if not self.dry_run:
            logging.info('updating database')
            errata_record.original_states = backuped_state
            await self.db.commit()

    async def restore(self):
        """
        Restore errata records from backups.
        """
        fpaths = [f for f in self.backup_dir.iterdir() if f.is_file()]
        for fpath in fpaths:
            logging.info('Restoring %s', fpath)
            errata_record_id = fpath.stem
            await self.restore_state(errata_record_id, fpath)

    async def fix_errata_gpg_key(self, errata_record_id: str):
        """
        Fix the GPG key for an errata record.

        Args:
            errata_record_id (str): Errata record ID.
        """
        errata_record = await self.get_errata_record(errata_record_id)
        if not errata_record:
            logging.error('Cant find errata_record %s', errata_record_id)
            return
        expected_key_id = await self.get_expected_key_id(errata_record)
        if not expected_key_id:
            logging.error(
                'Cant get expected gpg key id for %s', errata_record_id
            )
            return
        await self.update_state(expected_key_id, errata_record)


class ActionType(str, Enum):
    fix = "fix"
    restore = "restore"


class Args(BaseModel):
    action: ActionType = ActionType.fix
    issue_date_from: datetime
    issue_date_to: datetime
    dry_run: bool = False
    backup_before_update: bool = True
    backup_dir: Path = Path('/tmp')

    class Config:
        use_enum_values = True
        validate_assignment = True


logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s %(levelname)-8s %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('errata_fix_keys#205.log'),
    ],
)


def valid_date(s):
    try:
        return datetime.strptime(s, '%Y-%m-%d')
    except ValueError as exc:
        msg = f"Not a valid date: {s}."
        raise argparse.ArgumentTypeError(msg) from exc


def parse_args() -> Args:
    """
    Parse command-line arguments.

    Returns:
        Args: Parsed arguments.
    """
    parser = argparse.ArgumentParser(
        description='Set correct gpg key ids for Alma8 errata records\
                    or restore previously backed up records'
    )
    parser.add_argument(
        "--action",
        choices=[action.value for action in ActionType],
        default=ActionType.fix.value,
        required=False,
        help="fix: fix errata records, \
                            restore: restore previously backed up records",
    )
    parser.add_argument(
        '--issue_date_from',
        type=valid_date,
        required=True,
        help='Start date (format: YYYY-MM-DD)',
    )
    parser.add_argument(
        '--issue_date_to',
        type=valid_date,
        required=True,
        help='End date (format: YYYY-MM-DD)',
    )
    parser.add_argument(
        '--dry_run',
        action='store_true',
        required=False,
        default=False,
        help='Dont commit changes to database',
    )
    parser.add_argument(
        '--backup_before_update',
        action='store_true',
        required=False,
        default=True,
        help='backup errata state before commiting chagnes',
    )
    parser.add_argument(
        '--backup_dir',
        type=Path,
        required=False,
        default=Path('/tmp'),
        help='Directory to backup files to',
    )
    args = parser.parse_args()

    if args.issue_date_from > args.issue_date_to:
        parser.error('issue_date_from cannot be later than issue_date_to')

    return Args(**vars(args))


async def get_alma8_platform_id(db: AsyncSession) -> int:
    """
    Retrieve the platform ID for AlmaLinux 8.

    Args:
        db (AsyncSession): Asynchronous database session.

    Returns:
        int: Platform ID.
    """
    stmt = select(models.Platform.id).where(models.Platform.name == AL8_NAME)
    platform_id = await db.scalar(stmt)
    if not platform_id:
        raise ValueError(f'Cant get platform_id for {AL8_NAME}')
    return platform_id


async def get_almalinux8_errata_ids_to_fix(db: AsyncSession, args: Args):
    """
    Retrieve the IDs of AlmaLinux 8 errata records to fix.

    Args:
        db (AsyncSession): Asynchronous database session.
        args (Args): Parsed command-line arguments.

    Returns:
        List[str]: List of errata record IDs.
    """
    platform_id = await get_alma8_platform_id(db)
    stmt = (
        select(models.NewErrataRecord.id)
        .where(
            and_(
                models.NewErrataRecord.platform_id == platform_id,
                models.NewErrataRecord.issued_date.between(
                    args.issue_date_from, args.issue_date_to
                ),
            )
        )
        .order_by(asc(models.NewErrataRecord.id))
    )
    records = (await db.scalars(stmt)).all()
    return records


async def fix_records(args: Args):
    """
    Fix errata records based on the provided arguments.

    Args:
        args (Args): Parsed command-line arguments.
    """
    now_date = datetime.now().strftime('%Y-%m-%d_%H%M%S')
    full_backup_dir = args.backup_dir / Path(f'errata_fix_keys_bak_{now_date}')
    os.makedirs(full_backup_dir, exist_ok=True)
    logging.info('Starting GPG keyid fixing')
    async with asynccontextmanager(get_db)() as db:
        fixer = FixAlma8ErrataKeys(
            dry_run=args.dry_run,
            db=db,
            backup_dir=full_backup_dir,
            backup_before_update=args.backup_before_update,
        )
        errata_ids = await get_almalinux8_errata_ids_to_fix(db, args)
        for errata_id in errata_ids:
            logging.info('%s', errata_id)
            await fixer.fix_errata_gpg_key(errata_id)
    if args.backup_before_update:
        logging.info('Original states were backuped in %s', full_backup_dir)


async def restore_records_from_backup(backup_dir: Path):
    """
    Restore errata records from backups.

    Args:
        backup_dir (Path): Directory containing backup files.
    """
    logging.info('Restoring GPG id from %s', backup_dir)
    async with asynccontextmanager(get_db)() as db:
        fixer = FixAlma8ErrataKeys(dry_run=False, db=db, backup_dir=backup_dir)
        await fixer.restore()


async def main():
    """
    Main function.
    """
    args = parse_args()
    if args.action == 'fix':
        await fix_records(args)
    if args.action == 'restore':
        await restore_records_from_backup(args.backup_dir)


if __name__ == '__main__':
    asyncio.run(main())

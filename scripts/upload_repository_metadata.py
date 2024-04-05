import logging
import os.path
import sys
from argparse import ArgumentParser
from contextlib import asynccontextmanager
from io import BytesIO

from fastapi import UploadFile
from syncer import sync

from alws.dependencies import get_db
from alws.utils.uploader import MetadataUploader


def parse_args():
    parser = ArgumentParser('metadata-uploader')
    parser.add_argument('-r', '--repo-name', type=str, required=True)
    parser.add_argument('-c', '--comps-file', type=str, required=False)
    parser.add_argument('-m', '--modules-file', type=str, required=False)
    parser.add_argument('-d', '--dry-run', action='store_true')
    parser.add_argument('-v', '--verbose', action='store_true')
    return parser.parse_args()


async def main():
    args = parse_args()
    log_level = logging.DEBUG if args.verbose else logging.INFO
    logging.basicConfig(level=log_level)
    logger = logging.getLogger('metadata-uploader')
    logger.setLevel(log_level)
    if not args.modules_file and not args.comps_file:
        logger.error('Module or comps file should be specified')
        return 1
    module_content = None
    comps_content = None
    if args.modules_file:
        with open(os.path.abspath(os.path.expanduser(
                args.modules_file)), 'rt') as f:
            module_content = UploadFile(BytesIO(f.read().encode('utf-8')))
    if args.comps_file:
        with open(os.path.abspath(os.path.expanduser(
                args.comps_file)), 'rt') as f:
            comps_content = UploadFile(BytesIO(f.read().encode('utf-8')))
    async with asynccontextmanager(get_db)() as session:
        uploader = MetadataUploader(session, args.repo_name)
        await uploader.process_uploaded_files(
            module_content, comps_content, dry_run=args.dry_run)
    return 0


if __name__ == '__main__':
    sys.exit(sync(main()))

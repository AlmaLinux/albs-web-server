import argparse
import asyncio
import logging
import os
import sys
from contextlib import asynccontextmanager

from fastapi_sqla import open_async_session
from sqlalchemy import select
from sqlalchemy.orm import joinedload

sys.path.append(os.path.dirname(os.path.dirname(__file__)))

from alws.constants import ErrataPackageStatus
from alws.dependencies import get_async_db_key
from alws.models import (
    BuildTask,
    BuildTaskArtifact,
    ErrataPackage,
    ErrataRecord,
    ErrataToALBSPackage,
)
from alws.pulp_models import RpmPackage
from alws.utils.fastapi_sqla_setup import setup_all
from alws.utils.parsing import clean_release, parse_rpm_nevra
from alws.utils.pulp_utils import (
    get_rpm_packages_by_ids,
    get_uuid_from_pulp_href,
)

logging.basicConfig(
    format="%(message)s",
    level=logging.INFO,
    datefmt="%m-%d %H:%M:%S",
    handlers=[
        logging.StreamHandler(),
    ],
)


async def main(
    advisory_id: str,
    build_id: int,
    ignore_release: bool,
):
    new_entites = []
    logging.info(
        'Start updating errata_to_albs_packages for % advisory',
        advisory_id,
    )
    added = not_found = 0
    await setup_all()
    async with open_async_session(key=get_async_db_key()) as db:
        advisory = (
            (
                await db.execute(
                    select(ErrataRecord)
                    .where(ErrataRecord.id == advisory_id)
                    .options(
                        joinedload(ErrataRecord.packages).joinedload(
                            ErrataPackage.albs_packages
                        )
                    ),
                )
            )
            .scalars()
            .first()
        )
        if not advisory:
            logging.error('Advisory %s doesn`t exist', advisory_id)
            return
        build_artifacts = (
            (
                await db.execute(
                    select(BuildTaskArtifact).where(
                        BuildTaskArtifact.type == 'rpm',
                        BuildTaskArtifact.build_task_id.in_(
                            select(BuildTask.id)
                            .where(BuildTask.build_id == build_id)
                            .scalar_subquery()
                        ),
                    ),
                )
            )
            .scalars()
            .all()
        )
        build_pkgs_mapping = {
            get_uuid_from_pulp_href(artifact.href): artifact.id
            for artifact in build_artifacts
        }
        pulp_pkgs = get_rpm_packages_by_ids(
            list(build_pkgs_mapping),
            [
                RpmPackage.content_ptr_id,
                RpmPackage.name,
                RpmPackage.epoch,
                RpmPackage.version,
                RpmPackage.release,
                RpmPackage.arch,
                RpmPackage.rpm_sourcerpm,
            ],
        )
        for errata_pkg in advisory.packages:
            for errata_to_albs_pkg in errata_pkg.albs_packages:
                await db.delete(errata_to_albs_pkg)

            errata_pkg.source_srpm = None
            for pulp_pkg in pulp_pkgs.values():
                pulp_pkg_href = pulp_pkg.content_ptr_id
                if (
                    errata_pkg.name != pulp_pkg.name
                    or errata_pkg.version != pulp_pkg.version
                    or pulp_pkg.arch not in (errata_pkg.arch, 'noarch')
                    or (
                        not ignore_release
                        and clean_release(pulp_pkg.release)
                        != clean_release(errata_pkg.release)
                    )
                ):
                    continue
                new_errata_to_albs_pkg = ErrataToALBSPackage(
                    errata_package_id=errata_pkg.id,
                    albs_artifact_id=build_pkgs_mapping[pulp_pkg_href],
                    status=ErrataPackageStatus.proposal,
                    name=pulp_pkg.name,
                    arch=pulp_pkg.arch,
                    version=pulp_pkg.version,
                    release=pulp_pkg.release,
                    epoch=int(pulp_pkg.epoch),
                )
                for collection in (errata_pkg.albs_packages, new_entites):
                    collection.append(new_errata_to_albs_pkg)
                if errata_pkg.source_srpm is None:
                    nevra = parse_rpm_nevra(pulp_pkg.rpm_sourcerpm)
                    errata_pkg.source_srpm = nevra.name
                logging.info(
                    'Package %s has been added to %s',
                    pulp_pkg.nevra,
                    advisory_id,
                )
                added += 1
            if not errata_pkg.albs_packages:
                logging.warning(
                    'Cannot find match for %s',
                    f'{errata_pkg.name}-{errata_pkg.version}-{errata_pkg.release}.{errata_pkg.arch}',
                )
            not_found += 1
        db.add_all(new_entites)
    logging.info('Total: added %d, not found %d', added, not_found)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(
        'errata_pkgs_matcher',
        description='Removes linked errata_to_albs_packages to advisory and adds packages from build',
    )
    parser.add_argument('--advisory-id', type=str)
    parser.add_argument('--build-id', type=int)
    parser.add_argument(
        '--ignore-release-part',
        action='store_true',
        default=False,
        help='Ignore the release part in NEVRA during package matching (default: False)',
    )
    args = parser.parse_args()
    asyncio.run(
        main(
            advisory_id=args.advisory_id,
            build_id=args.build_id,
            ignore_release=args.ignore_release_part,
        )
    )

import asyncio
import logging
import re
import typing

import createrepo_c as cr
import yaml
from fastapi_sqla import open_async_session, open_session
from sqlalchemy import select
from sqlalchemy.orm import Session

from alws.config import settings
from alws.constants import ErrataPackageStatus, ErrataReferenceType
from alws.dependencies import get_async_db_key
from alws.models import ErrataRecord, ErrataReference
from alws.pulp_models import UpdatePackage, UpdateRecord
from alws.utils import pulp_client
from alws.utils.fastapi_sqla_setup import setup_all

logging.basicConfig(
    level=logging.DEBUG,
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('errata_fix_script.log'),
    ],
)


async def update_pulp_repo(repo, pulp):
    repo_name = repo["name"] + "-" + repo["arch"]
    logging.info("Updating for repo %s is started", repo_name)
    pulp_repo = await pulp.get_rpm_repository(repo_name)
    await pulp.create_rpm_publication(pulp_repo["pulp_href"])
    logging.info(f"Updating for repo {repo} is done")


async def prepare_albs_packages_cache(
    albs_db: Session,
    pulp: pulp_client.PulpClient,
    record_id: str,
) -> typing.Dict[str, typing.Any]:
    albs_packages_cache = {}
    pulp_pkg_fields = [
        'name',
        'location_href',
        'arch',
        'version',
        'pulp_href',
        'pkgId',
        'release',
        'epoch',
        'rpm_sourcerpm',
        'sha256',
        'checksum_type',
    ]
    albs_record: typing.Optional[ErrataRecord] = (
        albs_db.execute(
            select(ErrataRecord).where(ErrataRecord.id == record_id)
        )
        .scalars()
        .first()
    )
    if not albs_record:
        return albs_packages_cache
    logging.info('Collecting pulp_packages for record %s', record_id)
    for package in albs_record.packages:
        for albs_package in package.albs_packages:
            if albs_package.status != ErrataPackageStatus.released:
                continue
            pulp_pkg = await pulp.get_rpm_package(
                albs_package.get_pulp_href(),
                include_fields=pulp_pkg_fields,
            )
            pulp_pkg['reboot_suggested'] = (
                albs_package.errata_package.reboot_suggested
            )
            location_href = re.sub(r'^Packages/', '', pulp_pkg['location_href'])
            pulp_pkg['location_href'] = location_href
            albs_packages_cache[location_href] = pulp_pkg
    return albs_packages_cache


async def update_pulp_db():
    logging.info("Update pulp db is started")
    pulp = pulp_client.PulpClient(
        settings.pulp_host, settings.pulp_user, settings.pulp_password
    )
    albs_packages_cache = {}
    latest_record_id = ''
    logging.info('updating pulp db records')
    with open_session(key="pulp") as pulp_db, open_session() as albs_db:
        records: typing.List[UpdateRecord] = (
            pulp_db.execute(select(UpdateRecord).order_by(UpdateRecord.id))
            .scalars()
            .all()
        )
        for record in records:
            logging.info("Processing errata %s", record.id)
            if latest_record_id != record.id:
                albs_packages_cache = await prepare_albs_packages_cache(
                    albs_db, pulp, record.id
                )
            if not albs_packages_cache:
                logging.info(
                    'Skipping record %s, there is no ErrataRecord', record.id
                )
                continue
            collection = record.collections[0]
            collection_arch = re.search(
                r'i686|x86_64|aarch64|ppc64le|s390x',
                collection.name,
            ).group()
            logging.info('Start checking errata packages for %s', record.id)
            albs_packages = {
                location_href
                for location_href, pkg in albs_packages_cache.items()
                if pkg['arch'] in (collection_arch, 'noarch')
            }
            errata_packages = {pkg.filename for pkg in collection.packages}
            missing_filenames = albs_packages.difference(errata_packages)
            if not missing_filenames:
                logging.info('Errata %s is ok', record.id)
                continue
            for filename in missing_filenames:
                pulp_pkg = albs_packages_cache[filename]
                if (
                    pulp_pkg['sha256'] is None
                    and pulp_pkg['checksum_type'] == 'sha256'
                ):
                    logging.warning(
                        'sha256 sum is missing for %s using pkgId instead',
                        filename,
                    )
                    pulp_pkg['sha256'] = pulp_pkg['pkgId']
                collection.packages.append(
                    UpdatePackage(
                        name=pulp_pkg['name'],
                        filename=pulp_pkg['location_href'],
                        arch=pulp_pkg['arch'],
                        version=pulp_pkg['version'],
                        release=pulp_pkg['release'],
                        epoch=str(pulp_pkg['epoch']),
                        reboot_suggested=pulp_pkg['reboot_suggested'],
                        src=pulp_pkg['rpm_sourcerpm'],
                        sum=pulp_pkg['sha256'],
                        sum_type=cr.checksum_type('sha256'),
                    )
                )
                logging.info(
                    'Added package %s for errata %s', filename, record.id
                )
            logging.info('Start checking record %s references', record.id)
            for reference in record.references:
                if (
                    reference.title
                    or reference.ref_type == ErrataReferenceType.bugzilla.value
                ):
                    continue
                reference.title = reference.ref_id
                logging.info('Fixed ref_title for ref_id %s', reference.ref_id)
            latest_record_id = record.id
    logging.info('pulp db records updated')
    platforms = yaml.safe_load(
        open("reference_data/platforms.yaml", "r").read()
    )
    tasks = []
    for platform in platforms:
        for repo in platform["repositories"]:
            if not repo.get("production"):
                continue
            tasks.append(update_pulp_repo(repo, pulp))
    await asyncio.gather(*tasks)
    logging.info("Update pulp db is done")


async def update_albs_db():
    logging.info("Update albs db started")
    query = select(ErrataReference).where(
        ErrataReference.ref_type != ErrataReferenceType.bugzilla,
        ErrataReference.title == '',
    )
    async with open_async_session(key=get_async_db_key()) as db:
        for reference in (await db.execute(query)).scalars().all():
            reference.title = reference.ref_id
    logging.info("Update albs db is done")


async def main():
    pulp_client.PULP_SEMAPHORE = asyncio.Semaphore(10)
    tasks = [
        update_pulp_db(),
        update_albs_db(),
    ]
    await setup_all()
    await asyncio.gather(*tasks)


if __name__ == "__main__":
    asyncio.run(main())

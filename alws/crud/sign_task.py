import logging
import typing
import urllib.parse

from sqlalchemy.future import select
from sqlalchemy.orm import Session, selectinload

from alws import models
from alws.config import settings
from alws.constants import SignStatus
from alws.errors import BuildAlreadySignedError, DataNotFoundError
from alws.schemas import sign_schema
from alws.utils.debuginfo import is_debuginfo_rpm
from alws.utils.pulp_client import PulpClient


async def __get_build_repos(
        db: Session, build_id: int, build: models.Build = None) -> dict:
    if not build:
        builds = await db.execute(select(models.Build).where(
            models.Build.id == build_id).options(
            selectinload(models.Build.repos)
        ))
        build = builds.scalars().first()
    return {(repo.arch, repo.debug): repo for repo in build.repos
            if repo.type == 'rpm' and not repo.production}


def __get_package_url(base_url: str, package_name: str) -> str:
    pkg_first_letter = package_name[0]
    return urllib.parse.urljoin(
        base_url, f'Packages/{pkg_first_letter}/{package_name}')


async def get_sign_tasks(db: Session, build_id: int = None) \
        -> typing.List[models.SignTask]:
    query = select(models.SignTask)
    if build_id:
        query = query.where(models.SignTask.build_id == build_id)
    query = query.options(selectinload(models.SignTask.sign_key))
    result = await db.execute(query)
    return result.scalars().all()


async def create_sign_task(db: Session, payload: sign_schema.SignTaskCreate) \
        -> models.SignTask:
    async with db.begin():
        builds = await db.execute(select(models.Build).where(
            models.Build.id == payload.build_id).options(
                selectinload(models.Build.source_rpms),
                selectinload(models.Build.binary_rpms)
        ))
        build = builds.scalars().first()
        if not build:
            raise DataNotFoundError(
                f'Build with ID {payload.build_id} does not exist')
        if build.signed:
            raise BuildAlreadySignedError(
                f'Build with ID {payload.build_id} is already signed')
        if not build.source_rpms or not build.binary_rpms:
            raise ValueError(
                f'No built packages in build with ID {payload.build_id}')
        sign_keys = await db.execute(select(models.SignKey).where(
            models.SignKey.id == payload.sign_key_id))
        sign_key = sign_keys.scalars().first()

        if not sign_key:
            raise DataNotFoundError(
                f'Sign key with ID {payload.sign_key_id} does not exist')
        sign_task = models.SignTask(
            status=SignStatus.IDLE, build_id=payload.build_id,
            sign_key_id=payload.sign_key_id
        )
        db.add(sign_task)
        await db.commit()
    await db.refresh(sign_task)
    sign_tasks = await db.execute(select(models.SignTask).where(
        models.SignTask.id == sign_task.id).options(
        selectinload(models.SignTask.sign_key)))
    return sign_tasks.scalars().first()


async def get_available_sign_task(db: Session, key_ids: typing.List[str]):
    sign_tasks = await db.execute(select(models.SignTask).join(
        models.SignTask.sign_key).where(
            models.SignTask.status == SignStatus.IDLE,
            models.SignKey.keyid.in_(key_ids)
        ).options(selectinload(models.SignTask.sign_key))
    )
    sign_task = sign_tasks.scalars().first()
    if not sign_task:
        return {}

    sign_task.status = SignStatus.IN_PROGRESS
    db.add(sign_task)
    await db.commit()

    build_src_rpms = await db.execute(select(models.SourceRpm).where(
        models.SourceRpm.build_id == sign_task.build_id).options(
        selectinload(models.SourceRpm.artifact))
    )
    build_src_rpms = build_src_rpms.scalars().all()
    if not build_src_rpms:
        return {}
    build_binary_rpms = await db.execute(select(models.BinaryRpm).where(
        models.BinaryRpm.build_id == sign_task.build_id).options(
        selectinload(models.BinaryRpm.artifact).selectinload(
            models.BuildTaskArtifact.build_task)
        )
    )
    build_binary_rpms = build_binary_rpms.scalars().all()
    if not build_binary_rpms:
        return {}
    sign_task_payload = {'id': sign_task.id, 'build_id': sign_task.build_id,
                         'keyid': sign_task.sign_key.keyid}
    packages = []

    repo_mapping = await __get_build_repos(db, sign_task.build_id)
    repo = repo_mapping.get(('src', False))
    for src_rpm in build_src_rpms:
        packages.append(
            {
                'id': src_rpm.id,
                'name': src_rpm.artifact.name,
                'arch': 'src',
                'type': 'rpm',
                'download_url': __get_package_url(
                    repo.url, src_rpm.artifact.name)
            }
        )

    for binary_rpm in build_binary_rpms:
        debug = is_debuginfo_rpm(binary_rpm.artifact.name)
        repo = repo_mapping.get((binary_rpm.artifact.build_task.arch, debug))
        packages.append(
            {
                'id': binary_rpm.id,
                'name': binary_rpm.artifact.name,
                'arch': binary_rpm.artifact.build_task.arch,
                'type': 'rpm',
                'download_url': __get_package_url(
                    repo.url, binary_rpm.artifact.name)
            }
        )
    sign_task_payload['packages'] = packages
    return sign_task_payload


async def complete_sign_task(db: Session, sign_task_id: int,
                             payload: sign_schema.SignTaskComplete) \
        -> models.SignTask:
    async with db.begin():
        builds = await db.execute(select(models.Build).where(
            models.Build.id == payload.build_id).options(
            selectinload(models.Build.repos)))
        build = builds.scalars().first()
        source_rpms = await db.execute(select(models.SourceRpm).where(
            models.SourceRpm.build_id == payload.build_id).options(
            selectinload(models.SourceRpm.artifact)))
        source_rpms = source_rpms.scalars().all()
        binary_rpms = await db.execute(select(models.BinaryRpm).where(
            models.BinaryRpm.build_id == payload.build_id).options(
            selectinload(models.BinaryRpm.artifact)))
        binary_rpms = binary_rpms.scalars().all()

        all_rpms = source_rpms + binary_rpms
        modified_items = []
        repo_mapping = await __get_build_repos(
            db, payload.build_id, build=build)
        pulp_client = PulpClient(
            settings.pulp_host,
            settings.pulp_user,
            settings.pulp_password
        )
        sign_failed = False
        sign_tasks = await db.execute(select(models.SignTask).where(
            models.SignTask.id == sign_task_id
        ).options(selectinload(models.SignTask.sign_key)))
        sign_task = sign_tasks.scalars().first()

        if payload.packages:
            for package in payload.packages:
                # Check that package fingerprint matches the requested
                if package.fingerprint != sign_task.sign_key.fingerprint:
                    logging.error('Package %s is signed with a wrong GPG key %s, '
                                  'expected fingerprint: %s', package.name,
                                  package.fingerprint,
                                  sign_task.sign_key.fingerprint)
                    sign_failed = True
                    continue
                db_package = next(pkg for pkg in all_rpms
                                  if pkg.id == package.id)
                debug = is_debuginfo_rpm(package.name)
                repo = repo_mapping.get((package.arch, debug))
                new_pkg_href = await pulp_client.create_rpm_package(
                    package.name, package.href, repo.pulp_href)
                db_package.artifact.href = new_pkg_href
                db_package.artifact.sign_key = sign_task.sign_key
                modified_items.append(db_package)
                modified_items.append(db_package.artifact)

        if payload.success and not sign_failed:
            sign_task.status = SignStatus.COMPLETED
            build.signed = True
        else:
            sign_task.status = SignStatus.FAILED
            build.signed = False
        sign_task.log_href = payload.log_href
        sign_task.error_message = payload.error_message

        db.add(sign_task)
        db.add(build)
        if modified_items:
            db.add_all(modified_items)
        sign_tasks = await db.execute(select(models.SignTask).where(
            models.SignTask.id == sign_task_id).options(
            selectinload(models.SignTask.sign_key)))
        await db.commit()
    return sign_tasks.scalars().first()


async def verify_signed_build(db: Session, build_id: int,
                              platform_id: int) -> bool:
    async with db.begin():
        builds = await db.execute(select(models.Build).where(
            models.Build.id == build_id).options(
                selectinload(models.Build.source_rpms),
                selectinload(models.Build.binary_rpms)
        ))
        build = builds.scalars().first()
        if not build:
            raise DataNotFoundError(
                f'Build with ID {build_id} does not exist')
        if not build.signed == SignStatus.COMPLETED:
            raise ValueError(
                f'Build with ID {build_id} has not already signed')
        if not build.source_rpms or not build.binary_rpms:
            raise ValueError(
                f'No built packages in build with ID {build_id}')
        platform = await db.execute(select(models.Platform).where(
            models.Platform.id == platform_id).options(
                selectinload(models.Platform.sign_keys)))
        if not platform:
            raise DataNotFoundError(
                f'platform with ID {platform_id} does not exist')
        sign_key = platform.sign_keys.scalars().first()
        if not sign_key:
            raise DataNotFoundError(
                f'Sign key for Platform ID {platform_id} does not exist')
        source_rpms = await db.execute(select(models.SourceRpm).where(
            models.SourceRpm.build_id == build_id).options(
            selectinload(models.SourceRpm.artifact)))
        source_rpms = source_rpms.scalars().all()
        binary_rpms = await db.execute(select(models.BinaryRpm).where(
            models.BinaryRpm.build_id == build_id).options(
            selectinload(models.BinaryRpm.artifact)))
        binary_rpms = binary_rpms.scalars().all()

        all_rpms = source_rpms + binary_rpms
        for p in all_rpms:
            if p.signed_by_key != sign_key:
                raise DataNotFoundError(
                    f'Sign key with for pkg ID {p.id} is not matched '
                    f'by sign key for platform ID {platform_id}')
        await db.commit()
    return True

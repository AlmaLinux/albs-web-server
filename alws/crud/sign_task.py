import asyncio
import datetime
import logging
import typing
import urllib.parse
from collections import defaultdict

from sqlalchemy import or_, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.orm import selectinload

from alws import models
from alws.config import settings
from alws.constants import GenKeyStatus, SignStatus
from alws.crud.user import get_user
from alws.database import Session
from alws.errors import (
    BuildAlreadySignedError,
    DataNotFoundError,
    GenKeyError,
    PermissionDenied,
    SignError,
)
from alws.perms import actions
from alws.perms.authorization import can_perform
from alws.pulp_models import RpmPackage
from alws.schemas import sign_schema
from alws.utils.copr import create_product_sign_key_repo
from alws.utils.debuginfo import is_debuginfo_rpm
from alws.utils.pulp_client import PulpClient
from alws.utils.pulp_utils import get_rpm_packages_by_checksums


async def __get_build_repos(
    db: AsyncSession,
    build_id: int,
    build: typing.Optional[models.Build] = None,
) -> dict:
    if not build:
        builds = await db.execute(
            select(models.Build)
            .where(models.Build.id == build_id)
            .options(selectinload(models.Build.repos))
        )
        build = builds.scalars().first()
    return {
        (repo.arch, repo.debug): repo
        for repo in build.repos
        if repo.type == "rpm" and not repo.production
    }


def __get_package_url(base_url: str, package_name: str) -> str:
    pkg_first_letter = package_name[0].lower()
    return urllib.parse.urljoin(
        base_url, f"Packages/{pkg_first_letter}/{package_name}"
    )


async def get_sign_tasks(
    db: AsyncSession,
    build_id: typing.Optional[int] = None,
) -> typing.List[models.SignTask]:
    query = select(models.SignTask)
    if build_id:
        query = query.where(models.SignTask.build_id == build_id)
    query = query.options(selectinload(models.SignTask.sign_key))
    result = await db.execute(query)
    return result.scalars().all()


async def get_gen_key_task(
    db: AsyncSession,
    gen_key_task_id: int,
) -> models.GenKeyTask:
    gen_key_tasks = await db.execute(
        select(models.GenKeyTask)
        .where(models.GenKeyTask.id == gen_key_task_id)
        .options(
            selectinload(models.GenKeyTask.product).selectinload(
                models.Product.repositories
            ),
            selectinload(models.GenKeyTask.product).selectinload(
                models.Product.owner
            ),
            selectinload(models.GenKeyTask.product)
            .selectinload(models.Product.team)
            .selectinload(models.Team.roles),
        )
    )
    return gen_key_tasks.scalars().first()


async def create_gen_key_task(
    db: AsyncSession,
    product: models.Product,
    user: models.User,
) -> models.GenKeyTask:
    user = await get_user(db, user.id)
    if not can_perform(product, user, actions.GenKey.name):
        raise PermissionDenied(
            'User does not have permissions '
            'to generate sign key for that product'
        )
    gen_key_task = models.GenKeyTask(
        status=GenKeyStatus.IDLE,
        product=product,
        product_id=product.id,
    )
    db.add(gen_key_task)
    await db.commit()
    await db.refresh(gen_key_task)
    return await get_gen_key_task(db=db, gen_key_task_id=gen_key_task.id)


async def create_sign_task(
    db: AsyncSession,
    payload: sign_schema.SignTaskCreate,
    user_id: int,
) -> models.SignTask:
    async with db.begin():
        user = await get_user(db, user_id)
        builds = await db.execute(
            select(models.Build)
            .where(models.Build.id == payload.build_id)
            .options(
                selectinload(models.Build.source_rpms),
                selectinload(models.Build.binary_rpms),
                selectinload(models.Build.owner)
                .selectinload(models.User.roles)
                .selectinload(models.UserRole.actions),
                selectinload(models.Build.team)
                .selectinload(models.Team.roles)
                .selectinload(models.UserRole.actions),
            )
        )
        build = builds.scalars().first()
        if not build:
            raise DataNotFoundError(
                f"Build with ID {payload.build_id} does not exist"
            )
        if build.signed:
            raise BuildAlreadySignedError(
                f"Build with ID {payload.build_id} is already signed"
            )
        if not build.source_rpms or not build.binary_rpms:
            raise ValueError(
                f"No built packages in build with ID {payload.build_id}"
            )
        sign_keys = await db.execute(
            select(models.SignKey)
            .where(models.SignKey.id == payload.sign_key_id)
            .options(
                selectinload(models.SignKey.owner),
                selectinload(models.SignKey.roles).selectinload(
                    models.UserRole.actions
                ),
            )
        )
        sign_key = sign_keys.scalars().first()

        if not sign_key:
            raise DataNotFoundError(
                f"Sign key with ID {payload.sign_key_id} does not exist"
            )

        if not can_perform(build, user, actions.SignBuild.name):
            raise PermissionDenied(
                "User does not have permissions to sign this build"
            )
        if not can_perform(sign_key, user, actions.UseSignKey.name):
            raise PermissionDenied(
                "User does not have permissions to use this sign key"
            )

        sign_task = models.SignTask(
            status=SignStatus.IDLE,
            build_id=payload.build_id,
            sign_key_id=payload.sign_key_id,
        )
        db.add(sign_task)
        await db.commit()
    await db.refresh(sign_task)
    sign_tasks = await db.execute(
        select(models.SignTask)
        .where(models.SignTask.id == sign_task.id)
        .options(selectinload(models.SignTask.sign_key))
    )
    return sign_tasks.scalars().first()


async def get_available_gen_key_task(
    db: AsyncSession,
) -> typing.Optional[models.GenKeyTask]:
    async with db.begin():
        gen_key_tasks = await db.execute(
            select(models.GenKeyTask)
            .where(models.GenKeyTask.status == GenKeyStatus.IDLE)
            .options(
                selectinload(models.GenKeyTask.product).selectinload(
                    models.Product.owner
                ),
            )
        )
        gen_key_task = gen_key_tasks.scalars().first()
        if gen_key_task:
            await db.execute(
                update(models.GenKeyTask)
                .where(models.GenKeyTask.id == gen_key_task.id)
                .values(status=GenKeyStatus.IN_PROGRESS)
            )
    if gen_key_task:
        await db.refresh(gen_key_task)
    return gen_key_task


async def get_available_sign_task(
    db: AsyncSession,
    key_ids: typing.List[str],
) -> typing.Dict[str, typing.Any]:
    sign_tasks = await db.execute(
        select(models.SignTask)
        .join(models.SignTask.sign_key)
        .where(
            models.SignTask.status == SignStatus.IDLE,
            models.SignKey.keyid.in_(key_ids),
            or_(
                models.SignTask.ts <= datetime.datetime.utcnow(),
                models.SignTask.ts.is_(None),
            ),
        )
        .options(selectinload(models.SignTask.sign_key))
    )
    sign_task = sign_tasks.scalars().first()
    if not sign_task:
        return {}

    await db.execute(
        update(models.SignTask)
        .where(models.SignTask.id == sign_task.id)
        .values(status=SignStatus.IN_PROGRESS)
    )

    build_src_rpms = await db.execute(
        select(models.SourceRpm)
        .where(models.SourceRpm.build_id == sign_task.build_id)
        .options(selectinload(models.SourceRpm.artifact))
    )
    build_src_rpms = build_src_rpms.scalars().all()
    if not build_src_rpms:
        return {}
    build_binary_rpms = await db.execute(
        select(models.BinaryRpm)
        .where(models.BinaryRpm.build_id == sign_task.build_id)
        .options(
            selectinload(models.BinaryRpm.artifact).selectinload(
                models.BuildTaskArtifact.build_task
            )
        )
    )
    build_binary_rpms = build_binary_rpms.scalars().all()
    if not build_binary_rpms:
        return {}
    sign_task_payload = {
        "id": sign_task.id,
        "build_id": sign_task.build_id,
        "keyid": sign_task.sign_key.keyid,
    }
    packages = []

    repo_mapping = await __get_build_repos(db, sign_task.build_id)
    repo = repo_mapping.get(("src", False))
    for src_rpm in build_src_rpms:
        packages.append({
            "id": src_rpm.artifact.id,
            "name": src_rpm.artifact.name,
            "cas_hash": src_rpm.artifact.cas_hash,
            "arch": "src",
            "type": "rpm",
            "download_url": __get_package_url(repo.url, src_rpm.artifact.name),
        })

    for binary_rpm in build_binary_rpms:
        debug = is_debuginfo_rpm(binary_rpm.artifact.name)
        repo = repo_mapping.get((binary_rpm.artifact.build_task.arch, debug))
        packages.append({
            "id": binary_rpm.artifact.id,
            "name": binary_rpm.artifact.name,
            "cas_hash": binary_rpm.artifact.cas_hash,
            "arch": binary_rpm.artifact.build_task.arch,
            "type": "rpm",
            "download_url": __get_package_url(
                repo.url,
                binary_rpm.artifact.name,
            ),
        })
    sign_task_payload["packages"] = packages
    await db.commit()
    return sign_task_payload


async def get_sign_task(
    db: AsyncSession,
    sign_task_id: int,
) -> models.SignTask:
    sign_tasks = await db.execute(
        select(models.SignTask)
        .where(models.SignTask.id == sign_task_id)
        .options(selectinload(models.SignTask.sign_key))
    )
    return sign_tasks.scalars().first()


async def complete_gen_key_task(
    gen_key_task_id: int,
    payload: sign_schema.GenKeyTaskComplete,
    db: AsyncSession,
) -> typing.Optional[models.SignKey]:
    gen_key_task = await get_gen_key_task(
        db=db,
        gen_key_task_id=gen_key_task_id,
    )
    if not gen_key_task:
        raise GenKeyError(
            f'Gen key task with id "{gen_key_task_id}" is absent'
        )
    if payload.success:
        task_status = GenKeyStatus.COMPLETED
        error_message = None
    else:
        task_status = GenKeyStatus.FAILED
        error_message = payload.error_message
    await db.execute(
        update(models.GenKeyTask)
        .where(models.GenKeyTask.id == gen_key_task_id)
        .values(
            status=task_status,
            error_message=error_message,
        )
    )
    if not payload.success:
        return
    sign_key_repo = next(
        (r for r in gen_key_task.product.repositories if r.type == 'sign_key'),
        None,
    )
    pulp_client = PulpClient(
        settings.pulp_host,
        settings.pulp_user,
        settings.pulp_password,
    )
    if not sign_key_repo:
        repo_name, repo_url, repo_href = await create_product_sign_key_repo(
            pulp_client=pulp_client,
            owner_name=gen_key_task.product.owner.username,
            product_name=gen_key_task.product.name,
        )
        sign_key_repo = models.Repository(
            name=repo_name,
            url=repo_url,
            arch='sign_key',
            pulp_href=repo_href,
            debug=False,
            production=True,
        )
        db.add(sign_key_repo)
    result = await pulp_client.get_files(
        relative_path=payload.file_name,
    )
    if not result:
        await pulp_client.create_file(
            file_name=payload.file_name,
            artifact_href=payload.sign_key_href,
            repo=sign_key_repo.pulp_href,
        )
    sign_key_url = urllib.parse.urljoin(
        sign_key_repo.url,
        payload.file_name,
    )
    roles = [r for r in gen_key_task.product.team.roles if 'signer' in r.name]
    sign_key = models.SignKey(
        name=payload.key_name,
        description=f'Community key "{payload.key_name}"',
        is_community=True,
        keyid=payload.key_id,
        fingerprint=payload.fingerprint,
        public_url=sign_key_url,
        product_id=gen_key_task.product_id,
        product=gen_key_task.product,
        roles=roles,
    )
    db.add(sign_key)
    await db.commit()
    await db.refresh(sign_key)
    return sign_key


async def complete_sign_task(
    sign_task_id: int,
    payload: sign_schema.SignTaskComplete,
) -> models.SignTask:
    async def __process_single_package(
        pkg: sign_schema.SignedRpmInfo,
        pulp_db_packages: typing.Dict[str, RpmPackage],
    ) -> typing.Tuple[str, dict]:
        sha256 = None
        rpm_pkg = pulp_db_packages.get(pkg.sha256)
        if rpm_pkg:
            new_pkg_href = rpm_pkg.pulp_href
            sha256 = pkg.sha256
        else:
            new_pkg_href = await pulp_client.create_rpm_package(
                pkg.name, pkg.href
            )
            if new_pkg_href:
                package_info = await pulp_client.get_rpm_package(
                    new_pkg_href, include_fields=["sha256"]
                )
                sha256 = package_info["sha256"]
        logging.debug("Process single package %s", pkg.id)
        return pkg.name, {
            "id": pkg.id,
            "href": new_pkg_href,
            "sha256": sha256,
            "original_sha256": pkg.sha256,
            "cas_hash": pkg.cas_hash,
        }

    async def __failed_post_processing(
        task: models.SignTask,
        statistics: dict,
    ) -> models.SignTask:
        logging.info("Sign task %s failed", sign_task_id)
        finish_time = datetime.datetime.utcnow()
        statistics["web_server_processing_time"] = int(
            (finish_time - start_time).total_seconds()
        )
        task.stats = statistics
        task.status = SignStatus.FAILED
        db.add(task)
        await db.commit()
        await db.refresh(task)
        return task

    task_started_time = None
    if getattr(payload, "stats", None) and isinstance(payload.stats, dict):
        task_started_time = payload.stats.pop("sign_task_start_time", None)
        if task_started_time:
            task_started_time = datetime.datetime.fromisoformat(
                task_started_time,
            )
        stats = payload.stats.copy()
    else:
        stats = {}

    start_time = datetime.datetime.utcnow()
    similar_rpms_mapping = defaultdict(list)
    packages_to_add = defaultdict(list)
    srpms_mapping = defaultdict(list)

    logging.info("Start processing task %s", sign_task_id)
    async with Session() as db, db.begin():
        builds = await db.execute(
            select(models.Build)
            .where(models.Build.id == payload.build_id)
            .options(selectinload(models.Build.repos))
        )
        build = builds.scalars().first()
        source_rpms = await db.execute(
            select(models.SourceRpm)
            .where(models.SourceRpm.build_id == payload.build_id)
            .options(selectinload(models.SourceRpm.artifact))
        )
        source_rpms = source_rpms.scalars().all()
        binary_rpms = await db.execute(
            select(models.BinaryRpm)
            .where(models.BinaryRpm.build_id == payload.build_id)
            .options(selectinload(models.BinaryRpm.artifact))
        )
        binary_rpms = binary_rpms.scalars().all()

        for srpm in source_rpms:
            srpms_mapping[srpm.artifact.href].append(srpm.artifact)

        all_rpms = source_rpms + binary_rpms
        for rpm in all_rpms:
            similar_rpms_mapping[rpm.artifact.name].append(rpm)
        modified_items = []
        repo_mapping = await __get_build_repos(
            db, payload.build_id, build=build
        )
        pulp_client = PulpClient(
            settings.pulp_host, settings.pulp_user, settings.pulp_password
        )
        sign_failed = False
        sign_tasks = await db.execute(
            select(models.SignTask)
            .where(models.SignTask.id == sign_task_id)
            .options(selectinload(models.SignTask.sign_key))
        )
        sign_task = sign_tasks.scalars().first()

        if not payload.success:
            sign_task.status = SignStatus.FAILED
            sign_task.error_message = payload.error_message
            db.add(sign_task)
            logging.info("Sign task %s failed", sign_task_id)
            logging.info(payload.error_message)
            return sign_task

        if payload.packages:
            # Check packages sign fingerprint, if it's not matching then
            # fast-fail the process
            logging.debug("Check packages sign fingerprint")
            for package in payload.packages:
                # Check that package fingerprint matches the requested
                if package.fingerprint != sign_task.sign_key.fingerprint:
                    logging.error(
                        "Package %s is signed with a wrong GPG key %s, "
                        "expected fingerprint: %s",
                        package.name,
                        package.fingerprint,
                        sign_task.sign_key.fingerprint,
                    )
                    sign_failed = True
                    break
            if sign_failed:
                sign_task = await __failed_post_processing(sign_task, stats)
                return sign_task

            # Map packages to architectures to add them into proper repositories
            package_arches_mapping = defaultdict(set)
            # Make mapping for conversion (name-href mapping)
            packages_to_convert = {}
            for package in payload.packages:
                package_arches_mapping[package.name].add(package.arch)
                if package.name not in packages_to_convert:
                    packages_to_convert[package.name] = package
            pulp_db_packages = get_rpm_packages_by_checksums(
                [pkg.sha256 for pkg in packages_to_convert.values()],
            )
            logging.info("Start processing packages for task %s", sign_task_id)
            results = await asyncio.gather(*(
                __process_single_package(package, pulp_db_packages)
                for package in packages_to_convert.values()
            ))
            converted_packages = dict(results)
            logging.info(
                "Finish processing packages for task %s", sign_task_id
            )
            logging.info(
                "Updating href and add sign key for every srpm in project"
            )
            for pkg_name, pkg_info in converted_packages.items():
                new_href = pkg_info["href"]
                if not pkg_info["href"]:
                    logging.error("Package %s href is missing", pkg_name)
                    sign_failed = True
                    break
                if not pkg_info["sha256"]:
                    logging.error(
                        "Package %s sha256 checksum is missing", pkg_name
                    )
                    sign_failed = True
                    break
                if pkg_info["sha256"] != pkg_info["original_sha256"]:
                    logging.error("Package %s checksum differs", pkg_name)
                    sign_failed = True
                    break

                debug = is_debuginfo_rpm(pkg_name)

                for db_pkg in similar_rpms_mapping.get(pkg_name, []):
                    # we should update href and add sign key
                    # for every srpm in project
                    db_sprms = srpms_mapping.get(db_pkg.artifact.href, [])
                    for db_sprm in db_sprms:
                        db_sprm.href = new_href
                        db_sprm.sign_key = sign_task.sign_key
                        db_sprm.cas_hash = pkg_info["cas_hash"]
                        modified_items.append(db_sprm)

                    db_pkg.artifact.href = new_href
                    db_pkg.artifact.sign_key = sign_task.sign_key
                    db_pkg.artifact.cas_hash = pkg_info["cas_hash"]
                    modified_items.append(db_pkg)
                    modified_items.append(db_pkg.artifact)

                for arch in package_arches_mapping.get(pkg_name, []):
                    repo = repo_mapping[(arch, debug)]
                    packages_to_add[repo.pulp_href].append(new_href)

            if sign_failed:
                sign_task = await __failed_post_processing(sign_task, stats)
                return sign_task
            logging.info("Start modify repository for task %s", sign_task_id)
            await asyncio.gather(*(
                pulp_client.modify_repository(repo_href, add=packages)
                for repo_href, packages in packages_to_add.items()
            ))
            logging.info("Finish modify repository for task %s", sign_task_id)

        if payload.success and not sign_failed:
            sign_task.status = SignStatus.COMPLETED
            build.signed = True
        else:
            sign_task.status = SignStatus.FAILED
            build.signed = False
        sign_task.log_href = payload.log_href
        sign_task.error_message = payload.error_message

        finish_time = datetime.datetime.utcnow()
        stats["web_server_processing_time"] = int(
            (finish_time - start_time).total_seconds()
        )
        sign_task.stats = stats
        sign_task.started_at = task_started_time
        sign_task.finished_at = datetime.datetime.utcnow()

        db.add(sign_task)
        db.add(build)
        if modified_items:
            db.add_all(modified_items)
        logging.info("Sign task %s is finished", sign_task_id)
        return sign_task


async def verify_signed_build(
    db: AsyncSession,
    build_id: int,
    platform_id: int,
) -> bool:
    build = await db.execute(
        select(models.Build)
        .where(models.Build.id == build_id)
        .options(
            selectinload(models.Build.source_rpms).selectinload(
                models.SourceRpm.artifact
            ),
            selectinload(models.Build.binary_rpms).selectinload(
                models.BinaryRpm.artifact
            ),
        )
    )
    build = build.scalars().first()
    if not build:
        raise DataNotFoundError(f"Build with ID {build_id} does not exist")
    if not build.signed:
        raise SignError(f"Build with ID {build_id} has not already signed")
    if not build.source_rpms or not build.binary_rpms:
        raise ValueError(f"No built packages in build with ID {build_id}")
    platforms = await db.execute(
        select(models.Platform)
        .where(models.Platform.id == platform_id)
        .options(selectinload(models.Platform.sign_keys))
    )
    platform = platforms.scalars().first()
    if not platform:
        raise DataNotFoundError(
            f"platform with ID {platform_id} does not exist"
        )
    if not platform.sign_keys:
        raise DataNotFoundError(
            f"platform with ID {platform_id} connects with no keys"
        )
    sign_key = platform.sign_keys[0]
    if not sign_key:
        raise DataNotFoundError(
            f"Sign key for Platform ID {platform_id} does not exist"
        )

    all_rpms = build.source_rpms + build.binary_rpms
    for rpm in all_rpms:
        if rpm.artifact.sign_key != sign_key:
            raise SignError(
                f"Sign key with for pkg ID {rpm.id} is not matched "
                f"by sign key for platform ID {platform_id}"
            )
    return True

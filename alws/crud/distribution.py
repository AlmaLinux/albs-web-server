import collections

from sqlalchemy import delete
from sqlalchemy.future import select
from sqlalchemy.orm import Session, selectinload

from alws import models
from alws.config import settings
from alws.constants import BuildTaskStatus
from alws.errors import DistributionError
from alws.schemas import distro_schema, build_node_schema
from alws.utils.distro_utils import create_empty_repo
from alws.utils.pulp_client import PulpClient


async def create_distro(
        db: Session,
        distribution: distro_schema.DistroCreate
) -> models.Distribution:

    async with db.begin():
        db_distro = await db.execute(select(models.Distribution).where(
            models.Distribution.name.__eq__(distribution.name)))
        db_distro = db_distro.scalars().first()

        if db_distro:
            error_msg = f'{distribution.name} distribution already exists'
            raise DistributionError(error_msg)

        distro_platforms = await db.execute(select(models.Platform).where(
            models.Platform.name.in_(distribution.platforms)))
        distro_platforms = distro_platforms.scalars().all()

        db_distribution = models.Distribution(
            name=distribution.name
        )
        db_distribution.platforms.extend(distro_platforms)

        pulp_client = PulpClient(
            settings.pulp_host,
            settings.pulp_user,
            settings.pulp_password
        )
        await create_empty_repo(pulp_client, db_distribution)
        db.add(db_distribution)
        await db.commit()
    await db.refresh(db_distribution)
    return db_distribution


async def get_distributions(db):
    db_distros = await db.execute(select(models.Distribution))
    return db_distros.scalars().all()


async def add_distributions_after_rebuild(
        db: Session,
        request: build_node_schema.BuildDone,
):

    subquery = select(models.BuildTask.build_id).where(
        models.BuildTask.id == request.task_id).scalar_subquery()
    build_query = select(models.Build).where(
        models.Build.id == subquery,
    ).options(
        selectinload(models.Build.tasks).selectinload(
            models.BuildTask.artifacts),
        selectinload(models.Build.tasks).selectinload(
            models.BuildTask.rpm_module),
    )
    db_build = await db.execute(build_query)
    db_build = db_build.scalars().first()

    build_completed = all((
        task.status >= BuildTaskStatus.COMPLETED
        for task in db_build.tasks
    ))
    if not build_completed:
        return

    distr_query = select(models.Distribution).join(
        models.Distribution.builds,
    ).where(models.Build.id == db_build.id).options(
        selectinload(models.Distribution.builds),
        selectinload(models.Distribution.repositories),
    )
    db_distros = await db.execute(distr_query)
    db_distros = db_distros.scalars().all()

    pulp_client = PulpClient(settings.pulp_host, settings.pulp_user,
                             settings.pulp_password)

    for db_distro in db_distros:
        modify = await prepare_repo_modify_dict(db_build, db_distro)
        for modification in ('remove', 'add'):
            for key, value in modify.items():
                if modification == 'add':
                    await pulp_client.modify_repository(
                        add=value, repo_to=key)
                else:
                    await pulp_client.modify_repository(
                        remove=value, repo_to=key)
        for repo in modify.keys():
            await pulp_client.create_rpm_publication(repo)


async def prepare_repo_modify_dict(db_build: models.Build,
                                   db_distro: models.Distribution,
                                   existing_packages: dict = None):
    modify = collections.defaultdict(list)
    for task in db_build.tasks:
        if task.status != BuildTaskStatus.COMPLETED:
            continue
        if task.rpm_module:
            for distro_repo in db_distro.repositories:
                conditions = [
                    distro_repo.arch == task.arch,
                    not distro_repo.debug
                ]
                if all(conditions):
                    modify[distro_repo.pulp_href].append(
                        task.rpm_module.pulp_href)
        for artifact in task.artifacts:
            if artifact.type != 'rpm':
                continue
            build_artifact = build_node_schema.BuildDoneArtifact.from_orm(
                artifact)
            arch = task.arch
            if build_artifact.arch == 'src':
                arch = build_artifact.arch
            for distro_repo in db_distro.repositories:
                conditions = [
                    distro_repo.arch == arch,
                    distro_repo.debug == build_artifact.is_debuginfo
                ]
                if all(conditions):
                    if existing_packages:
                        repo_packages = existing_packages.get(
                            distro_repo.pulp_href, {})
                        if artifact.name in repo_packages:
                            continue
                    modify[distro_repo.pulp_href].append(build_artifact.href)
    final = {key: list(set(value)) for key, value in modify.items()}
    return final


async def get_existing_packages(pulp_client: PulpClient,
                                repository: models.Repository):
    return await pulp_client.get_rpm_repository_packages(
        repository.pulp_href,
        include_fields=['pulp_href', 'artifact', 'sha256', 'location_href'])


async def modify_distribution(build_id: int, distribution: str, db: Session,
                              modification: str):

    async with db.begin():
        db_distro = await db.execute(select(models.Distribution).where(
            models.Distribution.name.__eq__(distribution)
        ).options(selectinload(models.Distribution.repositories),
                  selectinload(models.Distribution.builds))
        )
        db_distro = db_distro.scalars().first()

        db_build = await db.execute(select(models.Build).where(
            models.Build.id.__eq__(build_id)
        ).options(
            selectinload(models.Build.tasks).selectinload(
                models.BuildTask.artifacts),
            selectinload(models.Build.tasks).selectinload(
                models.BuildTask.rpm_module)
        ))
        db_build = db_build.scalars().first()

        if modification == 'add':
            if db_build in db_distro.builds:
                error_msg = f'Packages of build {build_id} have already been' \
                            f' added to {distribution} distribution'
                raise DistributionError(error_msg)
        if modification == 'remove':
            if db_build not in db_distro.builds:
                error_msg = f'Packages of build {build_id} cannot be removed ' \
                            f'from {distribution} distribution ' \
                            f'as they are not added there'
                raise DistributionError(error_msg)

    pulp_client = PulpClient(settings.pulp_host, settings.pulp_user,
                             settings.pulp_password)
    existing_packages_mapping = {}
    for repo in db_distro.repositories:
        packages = await get_existing_packages(pulp_client, repo)
        existing_packages_mapping[repo.pulp_href] = {
            p['location_href']: p['pulp_href'] for p in packages
        }
    modify = await prepare_repo_modify_dict(db_build, db_distro)
    import pprint
    pprint.pprint(modify)
    for key, value in modify.items():
        if modification == 'add':
            await pulp_client.modify_repository(add=value, repo_to=key)
            db_distro.builds.append(db_build)
        else:
            await pulp_client.modify_repository(remove=value, repo_to=key)
        await pulp_client.create_rpm_publication(key)

    if modification == 'add':
        db_distro.builds.append(db_build)
    else:
        remove_query = models.Build.id.__eq__(build_id)
        await db.execute(
            delete(models.DistributionBuilds).where(remove_query)
        )
    db.add(db_distro)
    try:
        await db.commit()
    except Exception:
        await db.rollback()

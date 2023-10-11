import typing

import sqlalchemy
from sqlalchemy import delete
from sqlalchemy.future import select
from sqlalchemy.orm import Session, selectinload

from alws import models
from alws.config import settings
from alws.schemas import repository_schema, remote_schema
from alws.utils.pulp_client import PulpClient


async def get_repositories(
    db: Session,
    repository_id: int = None,
) -> typing.List[models.Repository]:
    repo_q = select(models.Repository)
    if repository_id:
        repo_q = repo_q.where(models.Repository.id == repository_id)
    result = await db.execute(repo_q)
    return result.scalars().all()


async def get_repositories_by_platform_name(
    db: Session,
    platform_name: str,
) -> typing.List[models.Repository]:
    result = await db.execute(
        select(models.Platform)
        .where(models.Platform.name == platform_name)
        .options(selectinload(models.Platform.repos))
    )
    result = result.scalars().first()
    if result is None:
        return []
    return result.repos


async def create_repositories(
    db: Session,
    payload: typing.List[repository_schema.RepositoryCreate],
) -> typing.List[models.Repository]:
    # We need to update existing repositories instead of trying to create
    # new ones if they have the same parameters
    query_list = [
        sqlalchemy.and_(
            models.Repository.name == item.name,
            models.Repository.arch == item.arch,
            models.Repository.type == item.type,
        )
        for item in payload
    ]
    query = sqlalchemy.or_(*query_list).with_for_update()
    repos_mapping = {}
    async with db.begin():
        repos_result = await db.execute(query)
        for repo in repos_result.scalars().all():
            repo_key = f'{repo.name}-{repo.arch}-{repo.debug}'
            repos_mapping[repo_key] = repo

        for repo_item in payload:
            repo_item_dict = repo_item.dict()
            repo_key = f'{repo_item.name}-{repo_item.arch}-{repo_item.debug}'
            if repo_key not in repos_mapping:
                repos_mapping[repo_key] = models.Repository(**repo_item_dict)
            else:
                repo = repos_mapping[repo_key]
                for field, value in repo_item_dict.items():
                    setattr(repo, field, value)

        db.add_all(repos_mapping.values())
        await db.commit()

    for repo in repos_mapping.values():
        await db.refresh(repo)

    return list(repos_mapping.values())


async def create_repository(
    db: Session,
    payload: repository_schema.RepositoryCreate,
) -> models.Repository:
    query = select(models.Repository).where(
        models.Repository.name == payload.name,
        models.Repository.arch == payload.arch,
        models.Repository.type == payload.type,
        models.Repository.debug == payload.debug,
    )
    async with db.begin():
        result = await db.execute(query)
        if result.scalars().first():
            raise ValueError('Repository already exists')
        repository = models.Repository(**payload.dict())
        db.add(repository)
    await db.refresh(repository)
    return repository


async def search_repository(
    db: Session,
    payload: repository_schema.RepositorySearch,
) -> models.Repository:
    query = select(models.Repository)
    for key, value in payload.dict().items():
        if key == 'name':
            query = query.where(models.Repository.name == value)
        elif key == 'arch':
            query = query.where(models.Repository.arch == value)
        elif key == 'type':
            query = query.where(models.Repository.type == value)
        elif key == 'debug':
            query = query.where(models.Repository.debug == value)
    async with db.begin():
        result = await db.execute(query)
        return result.scalars().first()


async def update_repository(
    db: Session,
    repository_id: int,
    payload: repository_schema.RepositoryUpdate,
) -> models.Repository:
    async with db.begin():
        db_repo = await db.execute(
            select(models.Repository).where(
                models.Repository.id == repository_id,
            )
        )
        db_repo = db_repo.scalars().first()
        for field, value in payload.dict().items():
            setattr(db_repo, field, value)
        db.add(db_repo)
        await db.commit()
    await db.refresh(db_repo)
    return db_repo


async def delete_repository(db: Session, repository_id: int):
    async with db.begin():
        await db.execute(
            delete(models.Repository).where(
                models.Repository.id == repository_id,
            )
        )
        await db.commit()


async def add_to_platform(
    db: Session,
    platform_id: int,
    repository_ids: typing.List[int],
) -> models.Platform:
    platform_result = await db.execute(
        select(models.Platform)
        .where(models.Platform.id == platform_id)
        .options(selectinload(models.Platform.repos))
        .with_for_update()
    )
    platform = platform_result.scalars().first()
    if not platform:
        raise ValueError(f'Platform with id {platform_id} is missing')
    repositories_result = await db.execute(
        select(models.Repository).where(
            models.Repository.id.in_(repository_ids)
        )
    )
    repositories = repositories_result.scalars().all()

    new_repos_list = list(set(repositories + platform.repos))

    platform.repos = new_repos_list
    db.add(platform)
    db.add_all(new_repos_list)
    await db.commit()

    platform_result = await db.execute(
        select(models.Platform)
        .where(models.Platform.id == platform_id)
        .options(selectinload(models.Platform.repos))
    )
    return platform_result.scalars().first()


async def remove_from_platform(
    db: Session,
    platform_id: int,
    repository_ids: typing.List[int],
) -> models.Platform:
    await db.execute(
        delete(models.PlatformRepo).where(
            models.PlatformRepo.c.platform_id == platform_id,
            models.PlatformRepo.c.repository_id.in_(repository_ids),
        )
    )
    await db.commit()

    platform_result = await db.execute(
        select(models.Platform)
        .where(models.Platform.id == platform_id)
        .options(selectinload(models.Platform.repos))
    )
    return platform_result.scalars().first()


async def create_repository_remote(
    db: Session,
    payload: remote_schema.RemoteCreate,
) -> models.RepositoryRemote:
    query = select(models.RepositoryRemote).where(
        models.RepositoryRemote.name == payload.name,
        models.RepositoryRemote.arch == payload.arch,
        models.RepositoryRemote.url == payload.url,
    )
    pulp_client = PulpClient(
        settings.pulp_host,
        settings.pulp_user,
        settings.pulp_password,
    )
    result = await db.execute(query)
    remote = result.scalars().first()
    pulp_remote = await pulp_client.get_rpm_remote(payload.name)
    # we need update db_remote according to pulp_remote in case if
    # we reset only pulp db
    if pulp_remote:
        remote_href = pulp_remote['pulp_href']
        await pulp_client.update_rpm_remote(
            remote_href,
            payload.url,
            remote_policy=payload.policy,
        )
    else:
        remote_href = await pulp_client.create_rpm_remote(
            payload.name,
            payload.url,
            remote_policy=payload.policy,
        )
    if remote:
        return remote
    remote = models.RepositoryRemote(
        name=payload.name,
        arch=payload.arch,
        url=payload.url,
        pulp_href=remote_href,
    )
    db.add(remote)
    await db.commit()
    await db.refresh(remote)
    return remote


async def update_repository_remote(
    db: Session,
    remote_id: int,
    payload: remote_schema.RemoteUpdate,
) -> models.RepositoryRemote:
    async with db.begin():
        result = await db.execute(
            select(models.RepositoryRemote).where(
                models.RepositoryRemote.id == remote_id
            )
        )
        remote = result.scalars().first()
        for key, value in payload.dict().items():
            setattr(remote, key, value)
        db.add(remote)
        await db.commit()
    await db.refresh(remote)
    return remote


async def sync_repo_from_remote(
    db: Session,
    repository_id: int,
    payload: repository_schema.RepositorySync,
    wait_for_result: bool = False,
):
    async with db.begin():
        repository = select(models.Repository).get(repository_id)
        remote = select(models.RepositoryRemote).get(payload.remote_id)

    pulp_client = PulpClient(
        settings.pulp_host,
        settings.pulp_user,
        settings.pulp_password,
    )
    return await pulp_client.sync_rpm_repo_from_remote(
        repository.pulp_href,
        remote.pulp_href,
        sync_policy=payload.sync_policy,
        wait_for_result=wait_for_result,
    )

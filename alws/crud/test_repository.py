import typing

from sqlalchemy import delete, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload
from sqlalchemy.sql.expression import func

from alws import models
from alws.errors import DataNotFoundError, TestRepositoryError
from alws.schemas import test_repository_schema


async def get_repositories(
    session: AsyncSession,
    page_number: typing.Optional[int] = None,
    repository_id: typing.Optional[int] = None,
    name: typing.Optional[str] = None,
) -> typing.Union[
    typing.List[models.TestRepository],
    typing.Dict[str, typing.Any],
    models.TestRepository,
]:
    def generate_query(count=False):
        query = (
            select(models.TestRepository)
            .order_by(models.TestRepository.id.desc())
            .options(joinedload(models.TestRepository.packages))
        )
        if name:
            query = query.where(models.TestRepository.name == name)
        if count:
            query = select(func.count(models.TestRepository.id))
        if page_number and not count:
            query = query.slice(10 * page_number - 10, 10 * page_number)
        return query

    if page_number:
        return {
            "test_repositories": (
                (await session.execute(generate_query()))
                .unique()
                .scalars()
                .all()
            ),
            "total_test_repositories": (
                (await session.execute(generate_query(count=True)))
                .unique()
                .scalar()
            ),
            "current_page": page_number,
        }

    if repository_id:
        query = generate_query().where(
            models.TestRepository.id == repository_id
        )
        db_repo = (await session.execute(query)).unique().scalars().first()
        return db_repo
    return (await session.execute(generate_query())).unique().scalars().all()


async def get_package_mapping(
    session: AsyncSession,
    package_id: typing.Optional[int] = None,
    name: typing.Optional[str] = None,
) -> typing.Union[
    typing.List[models.PackageTestRepository],
    models.PackageTestRepository,
]:
    def generate_query():
        query = select(models.PackageTestRepository).order_by(
            models.PackageTestRepository.id.desc()
        )
        if name:
            query = query.where(
                models.PackageTestRepository.package_name == name
            )
        return query

    if package_id:
        query = generate_query().where(
            models.PackageTestRepository.id == package_id
        )
        db_package = (await session.execute(query)).unique().scalars().first()
        return db_package
    return (await session.execute(generate_query())).unique().scalars().all()


async def create_package_mapping(
    session: AsyncSession,
    payload: test_repository_schema.PackageTestRepositoryCreate,
    test_repository_id: int,
    flush: bool = False,
) -> models.PackageTestRepository:
    test_repository = await get_repositories(
        session,
        repository_id=test_repository_id,
    )

    if not test_repository:
        raise DataNotFoundError(
            f"Unknown test repository ID: {test_repository_id}"
        )

    new_package = models.PackageTestRepository(
        **payload.model_dump(),
        test_repository_id=test_repository_id,
    )
    new_package.test_repository = test_repository
    session.add(new_package)
    if flush:
        await session.flush()
    else:
        await session.commit()
    await session.refresh(new_package)
    return new_package


async def bulk_create_package_mapping(
    session: AsyncSession,
    payload: typing.List[test_repository_schema.PackageTestRepositoryCreate],
    repository_id: int,
):
    test_repo = await get_repositories(
        session,
        repository_id=repository_id,
    )
    if not test_repo:
        raise DataNotFoundError(f"Unknown test repository ID: {repository_id}")
    existing_packages = [
        (pkg.package_name, pkg.folder_name) for pkg in test_repo.packages
    ]
    new_packages = [
        models.PackageTestRepository(
            **pkg.model_dump(),
            test_repository_id=repository_id,
        )
        for pkg in payload
        if (pkg.package_name, pkg.folder_name) not in existing_packages
    ]
    session.add_all(new_packages)
    await session.commit()


async def create_repository(
    session: AsyncSession,
    payload: test_repository_schema.TestRepositoryCreate,
    flush: bool = False,
) -> models.TestRepository:
    test_repository = (
        (
            await session.execute(
                select(models.TestRepository).where(
                    or_(
                        models.TestRepository.name == payload.name,
                        models.TestRepository.url == payload.url,
                    )
                )
            )
        )
        .scalars()
        .first()
    )

    if test_repository:
        raise TestRepositoryError("Test Repository already exists")

    repository = models.TestRepository(**payload.model_dump())
    session.add(repository)
    if flush:
        await session.flush()
    else:
        await session.commit()
    await session.refresh(repository)
    return repository


async def update_repository(
    session: AsyncSession,
    repository_id: int,
    payload: test_repository_schema.TestRepositoryUpdate,
) -> models.TestRepository:
    db_repo = await get_repositories(
        session,
        repository_id=repository_id,
    )
    if not db_repo:
        raise DataNotFoundError(f"Unknown test repository ID: {repository_id}")

    for field, value in payload.model_dump().items():
        setattr(db_repo, field, value)
    session.add(db_repo)
    await session.commit()
    await session.refresh(db_repo)
    return db_repo


async def delete_package_mapping(session: AsyncSession, package_id: int):
    db_package = await get_package_mapping(session, package_id=package_id)
    if not db_package:
        raise DataNotFoundError(f"Package={package_id} doesn`t exist")
    await session.delete(db_package)
    await session.commit()


async def bulk_delete_package_mapping(
    session: AsyncSession,
    package_ids: typing.List[int],
    repository_id: int,
):
    await session.execute(
        delete(models.PackageTestRepository).where(
            models.PackageTestRepository.id.in_(package_ids),
            models.PackageTestRepository.test_repository_id == repository_id,
        )
    )
    await session.commit()


async def delete_repository(session: AsyncSession, repository_id: int):
    db_repo = await get_repositories(session, repository_id=repository_id)
    if not db_repo:
        raise DataNotFoundError(
            f"Test repository={repository_id} doesn`t exist"
        )
    await session.delete(db_repo)
    await session.commit()

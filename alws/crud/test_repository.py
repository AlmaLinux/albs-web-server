import typing

from sqlalchemy import or_
from sqlalchemy.future import select
from sqlalchemy.orm import Session, joinedload
from sqlalchemy.sql.expression import func
from sqlalchemy.ext.asyncio import AsyncSession

from alws import models
from alws.schemas import test_repository_schema
from alws.errors import DataNotFoundError, TestRepositoryError


async def get_repositories(
    db: AsyncSession,
    page_number: int = None,
    repository_id: int = None,
    name: str = None,
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
            "test_repositories": (await db.execute(generate_query()))
            .unique()
            .scalars()
            .all(),
            "total_test_repositories": (await db.execute(generate_query(count=True)))
            .unique()
            .scalar(),
            "current_page": page_number,
        }

    if repository_id:
        query = generate_query().where(
            models.TestRepository.id == repository_id
        )
        db_repo = (await db.execute(query)).unique().scalars().first()
        return db_repo
    return (await db.execute(generate_query())).unique().scalars().all()


async def get_package_mapping(
    db: AsyncSession,
    package_id: int = None,
    name: str = None,
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
                models.PackageTestRepository.package_namename == name
            )
        return query

    if package_id:
        query = generate_query().where(
            models.PackageTestRepository.id == package_id
        )
        db_package = (await db.execute(query)).unique().scalars().first()
        return db_package
    return (await db.execute(generate_query())).unique().scalars().all()


async def create_package_mapping(
    db: AsyncSession,
    payload: test_repository_schema.PackageTestRepositoryCreate,
    test_repository_id: int,
    flush: bool = False,
):
    test_repository = (
        (
            await db.execute(
                select(models.TestRepository).where(
                    models.TestRepository.id == test_repository_id
                )
            )
        )
        .scalars()
        .first()
    )

    if not test_repository:
        raise DataNotFoundError(
            f"Unknown test repository ID: {test_repository_id}"
        )

    new_package = models.PackageTestRepository(
        package_name=payload.package_name,
        folder_name=payload.folder_name,
        url=payload.url,
        test_repository_id=test_repository_id,
    )
    new_package.test_repository = test_repository
    db.add(new_package)
    if flush:
        await db.flush()
    else:
        await db.commit()
    await db.refresh(new_package)
    return new_package


async def create_repository(
    db: AsyncSession,
    payload: test_repository_schema.TestRepositoryCreate,
    flush: bool = False,
):
    test_repository = (
        (
            await db.execute(
                select(models.TestRepository).where(
                    or_(
                        models.TestRepository.name == payload.name,
                        models.TestRepository.name == payload.url,
                    )
                )
            )
        )
        .scalars()
        .first()
    )

    if test_repository:
        raise TestRepositoryError("Test Repository already exists")

    repository = models.TestRepository(**payload.dict())
    db.add(repository)
    if flush:
        await db.flush()
    else:
        await db.commit()
    await db.refresh(repository)
    return repository


async def update_repository(
    db: AsyncSession,
    repository_id: int,
    payload: test_repository_schema.TestRepositoryUpdate,
) -> models.TestRepository:
    db_repo = await db.execute(
        select(models.TestRepository).where(
            models.TestRepository.id == repository_id
        )
    )
    db_repo = db_repo.scalars().first()
    if not db_repo:
        raise DataNotFoundError(
            f"Unknown test repository ID: {repository_id}"
        )

    for field, value in payload.dict().items():
        setattr(db_repo, field, value)
    db.add(db_repo)
    await db.commit()
    await db.refresh(db_repo)
    return db_repo


async def delete_package_mapping(db: AsyncSession, package_id: int):
    db_package = await get_package_mapping(db, package_id=package_id)
    if not db_package:
        raise DataNotFoundError(f"Package={package_id} doesn`t exist")
    await db.delete(db_package)
    await db.commit()


async def delete_repository(db: AsyncSession, repository_id: int):
    db_repo = await get_repositories(db, repository_id=repository_id)
    if not db_repo:
        raise DataNotFoundError(
            f"Test repository={repository_id} doesn`t exist"
        )
    await db.delete(db_repo)
    await db.commit()

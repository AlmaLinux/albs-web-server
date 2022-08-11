import typing

from sqlalchemy import update
from sqlalchemy.future import select
from sqlalchemy.orm import Session, selectinload

from alws import models


async def get_user(
            db: Session,
            user_id: typing.Optional[int] = None,
            user_name: typing.Optional[str] = None,
            user_email: typing.Optional[str] = None
        ) -> models.User:
    query = select(models.User).options(
        selectinload(models.User.roles).selectinload(models.UserRole.actions),
    )
    condition = models.User.id == user_id
    if user_name is not None:
        condition = models.User.name == user_name
    elif user_email is not None:
        condition = models.User.email == user_email
    db_user = await db.execute(query.where(condition))
    return db_user.scalars().first()


async def get_all_users(db: Session) -> typing.List[models.User]:
    db_users = await db.execute(select(models.User).options(
        selectinload(models.User.oauth_accounts)))
    return db_users.scalars().all()


async def activate_user(user_id: int, db: Session):
    await db.execute(update(models.User).where(
        models.User.id == user_id).values(is_verified=True, is_active=True))


async def deactivate_user(user_id: int, db: Session):
    await db.execute(update(models.User).where(
        models.User.id == user_id).values(is_verified=False, is_active=False))


async def make_superuser(user_id: int, db: Session):
    await db.execute(update(models.User).where(
        models.User.id == user_id).values(is_superuser=True))


async def make_usual_user(user_id: int, db: Session):
    await db.execute(update(models.User).where(
        models.User.id == user_id).values(is_superuser=False))

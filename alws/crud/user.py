import typing

from sqlalchemy.future import select
from sqlalchemy.orm import Session, selectinload

from alws import models


async def get_user(
            db: Session,
            user_id: typing.Optional[int] = None,
            user_name: typing.Optional[str] = None,
            user_email: typing.Optional[str] = None
        ) -> models.User:
    query = models.User.id == user_id
    if user_name is not None:
        query = models.User.name == user_name
    elif user_email is not None:
        query = models.User.email == user_email
    db_user = await db.execute(select(models.User).where(query))
    return db_user.scalars().first()


async def get_all_users(db: Session) -> typing.List[models.User]:
    db_users = await db.execute(select(models.User).options(
        selectinload(models.User.oauth_accounts)))
    return db_users.scalars().all()

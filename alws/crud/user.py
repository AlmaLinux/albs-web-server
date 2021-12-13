import typing

from sqlalchemy.future import select
from sqlalchemy.orm import Session

from alws import models
from alws.config import settings
from alws.schemas import user_schema
from alws.utils.github import get_user_github_token, get_github_user_info
from alws.utils.jwt_utils import generate_JWT_token



async def github_login(
            db: Session,
            user: user_schema.LoginGithub
        ) -> models.User:
    async with db.begin():
        github_user_token = await get_user_github_token(
            user.code,
            settings.github_client,
            settings.github_client_secret
        )
        github_info = await get_github_user_info(github_user_token)
        if not any(item for item in github_info['organizations']
                   if item['login'] == 'AlmaLinux'):
            return
        new_user = models.User(
            username=github_info['login'],
            email=github_info['email']
        )
        query = models.User.username == new_user.username
        db_user = await db.execute(select(models.User).where(
            query).with_for_update())
        db_user = db_user.scalars().first()
        if not db_user:
            db.add(new_user)
            db_user = new_user
            await db.flush()
        db_user.github_token = github_user_token
        db_user.jwt_token = generate_JWT_token(
            {'user_id': db_user.id},
            settings.jwt_secret,
            settings.jwt_algorithm
        )
        await db.commit()
    await db.refresh(db_user)
    return db_user


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
    db_users = await db.execute(select(models.User))
    return db_users.scalars().all()

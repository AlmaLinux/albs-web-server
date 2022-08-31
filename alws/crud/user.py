import typing

from sqlalchemy import update, delete
from sqlalchemy.future import select
from sqlalchemy.orm import Session, selectinload

from alws import models
from alws.errors import UserError
from alws.schemas import user_schema


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
    await db.commit()


async def deactivate_user(user_id: int, db: Session):
    await db.execute(update(models.User).where(
        models.User.id == user_id).values(is_verified=False, is_active=False))
    await db.commit()


async def make_superuser(user_id: int, db: Session):
    await db.execute(update(models.User).where(
        models.User.id == user_id).values(is_superuser=True))
    await db.commit()


async def make_usual_user(user_id: int, db: Session):
    await db.execute(update(models.User).where(
        models.User.id == user_id).values(is_superuser=False))
    await db.commit()


async def remove_user(user_id: int, db: Session):
    # Check that the user doesn't own valuable artifacts
    # Related and potential valuable artifacts are:
    #   - build_releases where owner_id == user_id
    #   - builds where owner_id == user_id and released == true
    #     - we delete unreleased builds?
    #   - platform_flavours where owner_id == user_id
    #   - platforms where owner_id == user_id
    #   - products where owner_id == user_id
    #   - repositories where owner_id == user_id and production == true
    #     - what do with do with repositories where production == false if we can delete?
    #   - sign_keys where owner_id == user_id?
    #   - teams where owner_id == user_id and if count(*) from products where team_id in (select id from teams where owner_id=user_id)?
    #     - we delete teams that don't have products?
    #
    # For now, we try to remove and if there are any linked artifacts to this user id
    # we will just fail and return a generic error.
    # TODO: Add more fine grained checks and return an appropriate
    # reason why a user can't be removed
    try:
        await db.execute(delete(models.User).where(
            models.User.id == user_id))
        await db.commit()
    except Exception as exc:
        message = f'The user {user_id} could not be removed: {str(exc)}'
        raise UserError(message) from exc

async def update_user(
        db: Session, user_id: int,
        payload: user_schema.UserUpdate):
    user = await get_user(db, user_id=user_id)
    if not user:
        raise UserError(f'User with ID {user_id} does not exist')
    for k, v in payload.dict().items():
        if v!= None: setattr(user, k, v)
    db.add(user)
    await db.commit()
    await db.refresh(user)

import typing

from fastapi import APIRouter, Depends, HTTPException, status

from alws.dependencies import JWTBearer, get_sync_db
from alws.crud import user as user_crud
from alws.schemas import user_schema


router = APIRouter(
    prefix='/users',
    tags=['users'],
)


@router.post('/login/github', response_model=user_schema.LoginResponse)
async def github_login_or_signup(user: user_schema.LoginGithub):
    with get_sync_db() as db:
        user = await user_crud.github_login(db, user)
        if not user:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail='You should be a part of AlmaLinux '
                       'GitHub organization to login.'
            )
        return user


@router.get(
    '/',
    dependencies=[Depends(JWTBearer())],
    response_model=user_schema.User
)
async def get_user(
            id: typing.Optional[int] = None,
            name: typing.Optional[str] = None,
            email: typing.Optional[str] = None,
        ):
    with get_sync_db() as db:
        db_user = await user_crud.get_user(db, id, name, email)
        if db_user is None:
            value = id or name or email
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f'User "{value}" is not found'
            )
        return db_user


@router.get(
    '/all_users',
    dependencies=[Depends(JWTBearer())],
    response_model=typing.List[user_schema.User],
)
async def get_all_users():
    with get_sync_db() as db:
        return await user_crud.get_all_users(db)

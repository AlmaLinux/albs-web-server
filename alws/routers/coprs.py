import typing

from fastapi import APIRouter, Depends
from sqlalchemy import select, and_
from sqlalchemy.orm import selectinload

from alws import database
from alws import models
from alws.dependencies import get_db, JWTBearer
from alws.schemas.copr_schema import CoprDistribution
from alws.utils.copr import generate_repo_config

copr_router = APIRouter(
    tags=['coprs'],
    dependencies=[Depends(JWTBearer())]
)


@copr_router.get('/api_3/project/search',
                 response_model=typing.List[CoprDistribution])
async def search_repos(
    name: str,
    db: database.Session = Depends(get_db),
):
    result = await db.execute(
        select(models.Distribution).where(
            models.Distribution.name == name,
        ).options(selectinload(models.Distribution.repositories)),
    )
    return result.scalars().all()


@copr_router.get('/api_3/project/list',
                 response_model=typing.List[CoprDistribution])
async def list_repos(
    ownername: str,
    db: database.Session = Depends(get_db),
):
    result = await db.execute(
        select(models.Distribution).where(
            models.Distribution.owner.name == ownername
        ).options(selectinload(models.Distribution.repositories)),
    )
    return result.scalars().all()


@copr_router.post('/coprs/{ownername}/{name}/repo/{platform}/dnf.repo')
async def get_dnf_repo_config(
    ownername: str,
    name: str,
    platform: str,
    arch: str,
    db: database.Session = Depends(get_db),
):
    full_name = f'{ownername}/{name}'
    chroot = f'{platform}-{arch}'
    db_distr = await db.execute(
        select(models.Distribution).where(and_(
            models.Distribution.name == name,
            models.Distribution.owner.name == ownername,
        )).options(
            selectinload(models.Distribution.repositories)
        ),
    )
    db_distr = db_distr.scalars().first()
    if not db_distr:
        return f'Copr dir {full_name} doesn`t exist'
    for distr_repo in db_distr.repositories:
        if chroot in distr_repo.name:
            return await generate_repo_config(distr_repo)
    return f'Chroot {chroot} doesn`t exist in {full_name}'

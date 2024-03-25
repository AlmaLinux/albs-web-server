from typing import List

from fastapi import APIRouter, Depends
from fastapi_sqla import AsyncSessionDependency
from sqlalchemy.ext.asyncio import AsyncSession

from alws.auth import get_current_user
from alws.crud import platform_flavors as pf_crud
from alws.dependencies import get_async_db_key
from alws.schemas import platform_flavors_schema as pf_schema

router = APIRouter(
    prefix='/platform_flavors',
    tags=['platform_flavors'],
    dependencies=[Depends(get_current_user)],
)


@router.post('/', response_model=pf_schema.FlavourResponse)
async def create_flavour(
    flavour: pf_schema.CreateFlavour,
    db: AsyncSession = Depends(AsyncSessionDependency(key=get_async_db_key())),
):
    return await pf_crud.create_flavour(db, flavour)


@router.patch('/', response_model=pf_schema.FlavourResponse)
async def update_flavour(
    flavour: pf_schema.UpdateFlavour,
    db: AsyncSession = Depends(AsyncSessionDependency(key=get_async_db_key())),
):
    return await pf_crud.update_flavour(db, flavour)


@router.get('/', response_model=List[pf_schema.FlavourResponse])
async def get_flavours(
    db: AsyncSession = Depends(AsyncSessionDependency(key=get_async_db_key())),
):
    return await pf_crud.list_flavours(db)

import typing

from fastapi import APIRouter, Depends, Form, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.orm import selectinload


from alws.auth import get_current_user
from alws.crud.products import get_products
from alws.dependencies import get_db
from alws.errors import PermissionDenied
from alws.models import User, Product, Repository, Build
from alws.perms import actions
from alws.perms.authorization import can_perform
from alws.utils.uploader import MetadataUploader

router = APIRouter(
    prefix="/uploads",
    tags=["uploads"],
    dependencies=[Depends(get_current_user)],
)

async def get_repo_object(session: AsyncSession, repository):
    products = (await session.execute(
        select(Product).filter(
            Product.repositories.any(Repository.name == repository)
            )
        )).scalars().all()
    if not products:
        products = []
        builds = (await session.execute(
            select(Build)
            .filter(Build.repos.any(Repository.name == repository))
            .options(selectinload(Build.products))
            )).scalars().all()
        for build in builds:
            products.append(build.products)
    return products

@router.post("/upload_repometada/")
async def upload_repometada(
    modules: typing.Optional[UploadFile] = None,
    comps: typing.Optional[UploadFile] = None,
    repository: str = Form(...),
    session: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    msg = ""
    uploader = MetadataUploader(session, repository)
    repo_objects = await get_repo_object(session, repository)
    for repo_obj in repo_objects:
        if not can_perform(repo_obj, user, actions.ReleaseToProduct.name):
            raise PermissionDenied(
                "User does not have permissions to upload repository metadata to the repository."
            )
    if modules is None and comps is None:
        return {"error": "there is nothing to upload"}
    updated_metadata = await uploader.process_uploaded_files(modules, comps)
    msg += f'{", ".join(updated_metadata)} in "{repository}" has been updated'
    return {"message": msg}

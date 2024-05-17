import typing

from fastapi import APIRouter, Depends, Form, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from alws.auth import get_current_user
from alws.crud import products as products_crud
from alws.crud import user as user_crud
from alws.dependencies import get_db
from alws.errors import PermissionDenied
from alws.models import User
from alws.perms import actions
from alws.perms.authorization import can_perform
from alws.utils.uploader import MetadataUploader

router = APIRouter(
    prefix="/uploads",
    tags=["uploads"],
    dependencies=[Depends(get_current_user)],
)


@router.post("/upload_repometada/")
async def upload_repometada(
    modules: typing.Optional[UploadFile] = None,
    comps: typing.Optional[UploadFile] = None,
    repository: str = Form(...),
    session: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    msg = ""
    user = await user_crud.get_user(session, user_id=user.id)
    uploader = MetadataUploader(session, repository)
    repo_product = await products_crud.get_repo_product(session, repository)
    if not repo_product:
        return {"error": f"couldn't find a product or build repository {repository}"}
    if not can_perform(repo_product, user, actions.ReleaseToProduct.name):
        raise PermissionDenied(
            f"User does not have permissions to upload repository metadata to the product {repo_product}."
        )
    if modules is None and comps is None:
        return {"error": "there is nothing to upload"}
    updated_metadata = await uploader.process_uploaded_files(modules, comps)
    msg += f'{", ".join(updated_metadata)} in "{repository}" has been updated'
    return {"message": msg}

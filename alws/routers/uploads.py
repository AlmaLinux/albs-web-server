import typing

from fastapi import APIRouter, Depends, Form, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from alws.auth import get_current_user
from alws.crud.products import get_products
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
    product_name: str = Form(...),
    session: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    msg = ""
    uploader = MetadataUploader(session, repository)
    product = get_products(session, product_name=product_name)
    if not can_perform(product, user, actions.ReleaseToProduct.name):
        raise PermissionDenied(
            "User does not have permissions to upload repository metadata."
        )
    if modules is None and comps is None:
        return {"error": "there is nothing to upload"}
    updated_metadata = await uploader.process_uploaded_files(modules, comps)
    msg += f'{", ".join(updated_metadata)} in "{repository}" has been updated'
    return {"message": msg}

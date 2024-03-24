import typing

from fastapi import APIRouter, Depends, Form, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from alws.auth import get_current_user
from alws.dependencies import get_db
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
):
    # Temporary disable modules.yaml upload
    msg = ""
    if modules:
        msg = (
            'Modules metadata upload is disabled, see '
            'https://github.com/AlmaLinux/build-system/issues/192\n'
        )
        modules = None
    uploader = MetadataUploader(session, repository)
    if modules is None and comps is None:
        return {"error": "there is nothing to upload"}
    updated_metadata = await uploader.process_uploaded_files(modules, comps)
    msg += f'{", ".join(updated_metadata)} in "{repository}" has been updated'
    return {"message": msg}

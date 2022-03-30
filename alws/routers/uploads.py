import typing

from fastapi import APIRouter, Depends, UploadFile, Form

from alws.dependencies import JWTBearer
from alws.utils.uploader import MetadataUploader


router = APIRouter(
    prefix='/uploads',
    tags=['uploads'],
    dependencies=[Depends(JWTBearer())]
)


@router.post('/upload_repometada/')
async def upload_repometada(
    modules: typing.Optional[UploadFile] = None,
    comps: typing.Optional[UploadFile] = None,
    repository: str = Form(...),
):
    uploader = MetadataUploader()
    if modules is None and comps is None:
        return {'error': 'there is nothing to upload'}
    updated_metadata = await uploader.process_uploaded_files(
        repository, modules, comps)
    msg = f'{", ".join(updated_metadata)} in "{repository}" has been updated'
    return {'message': msg}

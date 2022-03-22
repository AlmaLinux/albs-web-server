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
    await uploader.process_uploaded_files(repository, modules, comps)
    return {'message': f'{repository} metadata updated'}

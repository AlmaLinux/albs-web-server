from fastapi import Request
from fastapi.responses import JSONResponse

from alws.errors import UploadError


__all__ = ['handlers']


async def upload_error_handler(request: Request, exc: UploadError):
    return JSONResponse({'detail': exc.detail}, status_code=exc.status)


handlers = {UploadError: upload_error_handler}

from fastapi import Request
from fastapi.responses import JSONResponse

from alws.errors import BuildAlreadySignedError


__all__ = ['handlers']


async def build_is_already_signed_error_handler(request: Request, exc):
    return JSONResponse({'detail': str(exc)}, status_code=409)


handlers = {BuildAlreadySignedError: build_is_already_signed_error_handler}

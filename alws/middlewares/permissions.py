from fastapi import Request
from fastapi.responses import JSONResponse

from alws.errors import PermissionDenied


__all__ = ['handlers']


async def permissions_denied_handler(request: Request, exc):
    return JSONResponse(content={'detail': str(exc)}, status_code=403)


handlers = {PermissionDenied: permissions_denied_handler}

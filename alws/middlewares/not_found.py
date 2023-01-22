from fastapi import Request
from fastapi.responses import JSONResponse

from alws.errors import DataNotFoundError


__all__ = ['handlers']


async def not_found_handler(request: Request, exc):
    return JSONResponse(content={'detail': str(exc)}, status_code=404)


handlers = {DataNotFoundError: not_found_handler}

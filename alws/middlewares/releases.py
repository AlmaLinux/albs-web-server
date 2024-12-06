from fastapi import Request, status
from fastapi.responses import JSONResponse

from alws.errors import PlatformMissingError

__all__ = ['handlers']


async def incorrect_platform_error_handler(request: Request, exc):
    return JSONResponse(
        {'detail': str(exc)},
        status_code=status.HTTP_400_BAD_REQUEST,
    )


handlers = {
    PlatformMissingError: incorrect_platform_error_handler,
}

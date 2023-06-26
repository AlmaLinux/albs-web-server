from fastapi import Request, status
from fastapi.responses import JSONResponse

from alws.errors import EmptyBuildError

__all__ = ['handlers']


async def no_refs_to_build(request: Request, exc):
    return JSONResponse(
        content={
            'detail': [
                {
                    'msg': str(exc),
                },
            ],
        },
        status_code=status.HTTP_400_BAD_REQUEST,
    )


handlers = {
    EmptyBuildError: no_refs_to_build,
}

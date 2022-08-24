from fastapi import Request
from fastapi.responses import JSONResponse

from alws.errors import ProductError


__all__ = ['handlers']


async def product_error_handler(request: Request, exc):
    return JSONResponse({'detail': str(exc)}, status_code=400)


handlers = {ProductError: product_error_handler}

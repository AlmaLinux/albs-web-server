from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi_limiter.depends import RateLimiter
from fastapi_sqla import AsyncSessionDependency
from sqlalchemy.ext.asyncio import AsyncSession

from alws.crud import package_info
from alws.dependencies import get_async_db_key
from alws.errors import PlatformNotFoundError, RepositoriesNotFoundError
from alws.schemas import package_info_schema

public_router = APIRouter(
    prefix='/package_info',
    tags=['package_info'],
)


@public_router.get(
    '/',
    dependencies=[Depends(RateLimiter(times=5, seconds=1))],
    response_model=List[package_info_schema.PackageInfo],
)
async def get_package_info(
    name: str,
    almalinux_version: int,
    arch: Optional[str] = None,
    updated_after: Optional[str] = None,
    bs_db: AsyncSession = Depends(
        AsyncSessionDependency(key=get_async_db_key())
    ),
    pulp_db: AsyncSession = Depends(AsyncSessionDependency(key='pulp_async')),
):
    """
    Get information about packages from the AlmaLinux production repositories.
    """
    platform_name = f'AlmaLinux-{almalinux_version}'
    try:
        packages = await package_info.get_package_info(
            bs_db,
            pulp_db,
            name,
            platform_name,
            arch,
            updated_after,
        )
        return packages
    except (PlatformNotFoundError, RepositoriesNotFoundError) as exc:
        raise HTTPException(
            detail=str(exc),
            status_code=status.HTTP_400_BAD_REQUEST,
        ) from exc
    except Exception as exc:
        raise HTTPException(
            detail=str(exc),
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        ) from exc

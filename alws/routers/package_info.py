from typing import List, Optional

from fastapi import APIRouter, Depends
from fastapi_limiter.depends import RateLimiter

from alws.config import settings
from alws.schemas import package_info_shema
from alws.utils.pulp_client import PulpClient

public_router = APIRouter(
    prefix='/package_info',
    tags=['package_info'],
)


@public_router.get(
    '/',
    dependencies=[Depends(RateLimiter(times=5, seconds=1))],
    response_model=List[package_info_shema.PackageInfo],
)
async def get_change_log(
    package_name: str,
    major_version: Optional[int] = None,
):
    pulp_client = PulpClient(
        settings.pulp_host, settings.pulp_user, settings.pulp_password
    )
    search_params = {"name": package_name}
    if major_version:
        search_params["version"] = 0
    packages = await pulp_client.get_rpm_packages(
        include_fields=[
            "name",
            "version",
            "release",
            "arch",
            "changelogs",
        ],
        name=package_name,
    )
    if major_version:
        release_str = f"el{major_version}"
        packages = [
            package for package in packages if release_str in package['release']
        ]
    return packages

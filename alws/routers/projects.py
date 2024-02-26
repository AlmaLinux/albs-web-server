import typing

from fastapi import APIRouter, Depends
import aioredis

from alws.auth import get_current_user
from alws.dependencies import get_redis
from alws.schemas import project_schema
from alws.scripts.git_cacher.git_cacher import (
    Config as Cacher_config,
    load_redis_cache
)


router = APIRouter(
    prefix='/projects',
    tags=['projects'],
    dependencies=[Depends(get_current_user)]
)


@router.get('/alma', response_model=typing.List[project_schema.Project])
async def list_alma_projects(
            redis: aioredis.Redis = Depends(get_redis)
        ):
    config = Cacher_config()
    cache = await load_redis_cache(redis, config.git_cache_keys['rpms'])
    return list(cache.values())


@router.get(
    '/alma/modularity',
    response_model=typing.List[project_schema.Project]
)
async def list_alma_modules(
            redis: aioredis.Redis = Depends(get_redis)
        ):
    config = Cacher_config()
    cache = await load_redis_cache(redis, config.git_cache_keys['modules'])
    return list(cache.values())

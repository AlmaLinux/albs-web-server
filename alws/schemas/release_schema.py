import datetime
import typing

from alws.schemas.perf_stats_schema import PerformanceStats
from alws.schemas.platform_schema import Platform
from alws.schemas.user_schema import User
from pydantic import BaseModel

__all__ = [
    'Release',
    'ReleaseCommitResult',
    'ReleaseCreate',
    'ReleaseUpdate',
]


class ReleaseProduct(BaseModel):
    id: int
    name: str
    title: typing.Optional[str] = None
    description: typing.Optional[str] = None
    is_community: bool

    class Config:
        from_attributes = True


class Release(BaseModel):
    id: int
    status: int
    build_ids: typing.List[int]
    build_task_ids: typing.Optional[typing.List[int]] = []
    plan: typing.Optional[typing.Dict[str, typing.Any]] = None
    owner: User
    platform: Platform
    product: ReleaseProduct
    performance_stats: typing.Optional[typing.List[PerformanceStats]] = None
    created_at: typing.Optional[datetime.datetime] = None

    class Config:
        from_attributes = True


class ReleaseResponse(BaseModel):

    releases: typing.List[Release]
    total_releases: typing.Optional[int] = None
    current_page: typing.Optional[int] = None


class ReleaseCreate(BaseModel):
    builds: typing.List[int]
    build_tasks: typing.Optional[typing.List[int]] = None
    platform_id: int
    product_id: int


class ReleaseUpdate(BaseModel):
    builds: typing.Optional[typing.List[int]] = None
    build_tasks: typing.Optional[typing.List[int]] = None
    plan: typing.Optional[typing.Dict[str, typing.Any]] = None


class ReleaseCommitResult(BaseModel):
    message: str

from typing import List, Optional, Union

from pydantic import BaseModel

from alws.schemas.perf_stats_schema import PerformanceStats

__all__ = ['TestTaskResult']


class TestTaskResult(BaseModel):
    api_version: str
    result: dict
    stats: Optional[dict] = None


class TestTask(BaseModel):
    id: int
    package_name: str
    package_version: str
    package_release: Optional[str] = None
    status: int
    revision: int
    alts_response: Optional[dict] = None
    performance_stats: Optional[List[PerformanceStats]] = None

    class Config:
        from_attributes = True


class TestLog(BaseModel):
    id: int
    log: str
    log_name: str
    success: bool
    logs_format: str
    tap_results: List[dict]


class TestTaskPayload(BaseModel):
    runner_type: str
    dist_name: str
    dist_version: Union[str, int]
    dist_arch: str
    package_name: str
    package_version: str
    callback_href: str
    repositories: Optional[List[dict]] = None
    module_name: Optional[str] = None
    module_stream: Optional[str] = None
    module_version: Optional[str] = None
    test_configuration: Optional[dict] = None

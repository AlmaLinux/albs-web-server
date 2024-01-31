import typing

from pydantic import BaseModel

__all__ = ['PerformanceStats']


class PerformanceStats(BaseModel):
    id: int
    build_task_id: typing.Optional[int] = None
    test_task_id: typing.Optional[int] = None
    release_id: typing.Optional[int] = None
    statistics: typing.Optional[dict] = None

    class Config:
        from_attributes = True

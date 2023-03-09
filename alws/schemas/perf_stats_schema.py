import typing

from pydantic import BaseModel


__all__ = ['PerformanceStats']


class PerformanceStats(BaseModel):
    id: int
    build_task_id: typing.Optional[int]
    test_task_id: typing.Optional[int]
    release_id: typing.Optional[int]
    statistics: typing.Optional[dict]

    class Config:
        orm_mode = True

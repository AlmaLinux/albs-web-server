import typing

from pydantic import BaseModel


__all__ = ['TestTaskResult']


class TestTaskResult(BaseModel):
    api_version: str
    result: dict


class TestTask(BaseModel):
    id: int
    build_id: typing.Optional[int]
    package_name: str
    package_version: str
    package_release: typing.Optional[str]
    status: int
    revision: int
    alts_response: typing.Optional[dict]

    class Config:
        orm_mode = True


class TestLog(BaseModel):
    id: int
    log: str
    success: bool
    logs_format: str
    tap_results: typing.List[dict]

import typing

from pydantic import BaseModel


__all__ = ['TestTaskResult']


class TestTaskResult(BaseModel):
    api_version: str
    result: dict

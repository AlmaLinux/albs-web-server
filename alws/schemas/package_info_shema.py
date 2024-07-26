from typing import List

from pydantic import BaseModel

__all__ = ['PackageInfo']


class PackageInfo(BaseModel):
    name: str
    version: str
    release: str
    arch: str
    changelogs: List

    class Config:
        from_attributes = True

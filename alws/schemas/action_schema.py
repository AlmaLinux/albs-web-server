import typing

from pydantic import BaseModel


__all__ = ['Action']


class Action(BaseModel):
    id: int
    name: str
    description: typing.Optional[str]

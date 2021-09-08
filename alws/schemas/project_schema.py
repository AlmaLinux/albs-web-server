import typing

import pydantic


class Project(pydantic.BaseModel):

    name: str
    clone_url: str
    tags: typing.List[str]
    branches: typing.List[str]

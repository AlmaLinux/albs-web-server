import typing

from pydantic import BaseModel


class SignDoneArtifact(BaseModel):

    name: str
    type: typing.Literal['rpm', 'build_log']
    href: str


class SignDone(BaseModel):

    task_id: int
    status: typing.Literal['done', 'failed', 'excluded']
    artifacts: typing.List[SignDoneArtifact]


class RequestSignStart(BaseModel):

    pgp_key_id: str


class SignStartDone(BaseModel):

    task_id: int


class RequestBuildTask(BaseModel):

    supported_arches: typing.List[str]


class RequestSignTask(BaseModel):

    pgp_keyids: typing.List[str]

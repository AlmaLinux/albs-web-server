import typing
from datetime import datetime

from pydantic import BaseModel, Field


class SignKey(BaseModel):
    id: int
    name: str
    description: str
    keyid: str
    public_url: str
    inserted: datetime

    class Config:
        orm_mode = True


class SignKeyCreate(BaseModel):
    name: str
    description: str
    keyid: str
    fingerprint: str
    public_url: str


class SignKeyUpdate(BaseModel):
    name: typing.Optional[str]
    description: typing.Optional[str]
    keyid: typing.Optional[str]
    fingerprint: typing.Optional[str]
    public_url: typing.Optional[str]


class SignTask(BaseModel):
    id: int
    build_id: int
    sign_key: SignKey
    status: int
    error_message: typing.Optional[str]
    log_href: typing.Optional[str]

    class Config:
        orm_mode = True


class SignTaskCreate(BaseModel):
    build_id: int
    sign_key_id: int


class SignTaskGet(BaseModel):
    key_ids: typing.List[str]


class SignRpmInfo(BaseModel):
    id: int
    name: str
    arch: typing.Optional[str]
    type: str
    download_url: str


class SignedRpmInfo(BaseModel):
    id: int
    name: str
    arch: typing.Optional[str]
    type: str
    href: str
    fingerprint: str


class AvailableSignTask(BaseModel):
    id: typing.Optional[int]
    build_id: typing.Optional[int]
    keyid: typing.Optional[str]
    packages: typing.Optional[typing.List[SignRpmInfo]]


class SignTaskComplete(BaseModel):
    build_id: int
    success: bool
    error_message: typing.Optional[str]
    log_href: typing.Optional[str]
    packages: typing.Optional[typing.List[SignedRpmInfo]]


class SignTaskCompleteResponse(BaseModel):
    success: bool

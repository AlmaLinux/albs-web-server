import typing
from datetime import datetime

from pydantic import BaseModel


class SignKey(BaseModel):
    id: int
    name: str
    description: str
    keyid: str
    public_url: str
    inserted: datetime
    platform_id: typing.Optional[int] = None
    product_id: typing.Optional[int] = None

    class Config:
        from_attributes = True


class SignKeyCreate(BaseModel):
    name: str
    description: str
    keyid: str
    fingerprint: str
    public_url: str
    platform_id: typing.Optional[int] = None


class SignKeyUpdate(BaseModel):
    name: typing.Optional[str] = None
    description: typing.Optional[str] = None
    keyid: typing.Optional[str] = None
    fingerprint: typing.Optional[str] = None
    public_url: typing.Optional[str] = None


class SignTask(BaseModel):
    id: int
    build_id: int
    sign_key: SignKey
    status: int
    error_message: typing.Optional[str] = None
    log_href: typing.Optional[str] = None

    class Config:
        from_attributes = True


class GenKeyTask(BaseModel):
    id: int
    user_name: typing.Optional[str] = None
    user_email: typing.Optional[str] = None
    product_name: typing.Optional[str] = None


class SignTaskCreate(BaseModel):
    build_id: int
    sign_key_id: int


class SignTaskGet(BaseModel):
    key_ids: typing.List[str]


class SignRpmInfo(BaseModel):
    id: int
    name: str
    arch: typing.Optional[str] = None
    type: str
    download_url: str
    cas_hash: typing.Optional[str] = None


class SignedRpmInfo(BaseModel):
    id: int
    name: str
    arch: typing.Optional[str] = None
    type: str
    href: str
    fingerprint: str
    sha256: str
    cas_hash: typing.Optional[str] = None


class AvailableSignTask(BaseModel):
    id: typing.Optional[int] = None
    build_id: typing.Optional[int] = None
    keyid: typing.Optional[str] = None
    packages: typing.Optional[typing.List[SignRpmInfo]] = None


class AvailableGenKeyTask(BaseModel):
    id: typing.Optional[int] = None
    user_name: typing.Optional[str] = None
    user_email: typing.Optional[str] = None
    product_name: typing.Optional[str] = None


class GenKeyTaskComplete(BaseModel):
    success: bool
    error_message: typing.Optional[str] = None
    sign_key_href: typing.Optional[str] = None
    key_name: typing.Optional[str] = None
    key_id: typing.Optional[str] = None
    fingerprint: typing.Optional[str] = None
    file_name: typing.Optional[str] = None


class SignTaskComplete(BaseModel):
    build_id: int
    success: bool
    error_message: typing.Optional[str] = None
    log_href: typing.Optional[str] = None
    packages: typing.Optional[typing.List[SignedRpmInfo]] = None
    stats: typing.Optional[dict] = None


class SignTaskCompleteResponse(BaseModel):
    success: bool


class SyncSignTaskRequest(BaseModel):
    content: str
    pgp_keyid: str
    sig_type: typing.Literal['detach-sign', 'clear-sign'] = 'detach-sign'


class SyncSignTaskResponse(BaseModel):
    asc_content: str


class SyncSignTaskError(BaseModel):
    error: str

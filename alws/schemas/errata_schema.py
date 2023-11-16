import datetime
from typing import Any, List, Optional

from pydantic import BaseModel, field_validator

from alws.constants import ErrataReleaseStatus
from alws.models import ErrataPackageStatus


class BaseErrataCVE(BaseModel):
    id: str
    cvss3: str
    cwe: Optional[str] = None
    impact: str
    public: str

    class Config:
        from_attributes = True


class BaseErrataReference(BaseModel):
    href: str
    ref_id: str
    ref_type: str
    title: Optional[str] = None
    cve: Optional[BaseErrataCVE] = None

    @field_validator("ref_type", mode="before")
    def validator_ref_type(cls, value):
        return str(value)


class ErrataReference(BaseErrataReference):
    id: int

    class Config:
        from_attributes = True


class BaseErrataPackage(BaseModel):
    name: str
    version: str
    release: str
    epoch: int
    arch: str
    reboot_suggested: bool

    class Config:
        from_attributes = True


class AlbsPackage(BaseModel):
    id: int
    albs_artifact_id: Optional[int] = None
    build_id: Optional[int] = None
    task_id: Optional[int] = None
    name: Optional[str] = None
    status: str

    @field_validator("status", mode="before")
    def status_validator(cls, status):
        return status.value

    class Config:
        from_attributes = True


class ErrataPackage(BaseErrataPackage):
    id: int
    source_srpm: Optional[str] = None
    albs_packages: List[AlbsPackage]

    class Config:
        from_attributes = True


class BaseErrataRecord(BaseModel):
    id: str
    freezed: bool
    platform_id: int
    issued_date: datetime.date
    updated_date: datetime.date
    title: str
    description: str
    status: str
    version: str
    severity: str
    rights: str
    definition_id: str
    definition_version: str
    definition_class: str
    affected_cpe: List[str]
    criteria: Any
    tests: Any
    objects: Any
    states: Any
    variables: Any
    references: List[BaseErrataReference]
    packages: List[BaseErrataPackage]


class ErrataRecord(BaseErrataRecord):
    references: List[ErrataReference]
    packages: List[ErrataPackage]
    title: Optional[str] = None
    original_title: str
    description: Optional[str] = None
    original_description: str
    release_status: Optional[ErrataReleaseStatus] = None
    last_release_log: Optional[str] = None

    class Config:
        from_attributes = True


class ErrataListResponse(BaseModel):
    records: List[ErrataRecord]
    total_records: Optional[int] = None
    current_page: Optional[int] = None


class CompactErrataRecord(BaseModel):
    id: str
    updated_date: datetime.date


class CreateErrataResponse(BaseModel):
    ok: bool


class ChangeErrataPackageStatusResponse(BaseModel):
    ok: bool
    error: Optional[str] = None


class ChangeErrataPackageStatusRequest(BaseModel):
    errata_record_id: str
    build_id: int
    source: str
    status: ErrataPackageStatus


class UpdateErrataRequest(BaseModel):
    errata_record_id: str
    title: Optional[str] = None
    description: Optional[str] = None


class ReleaseErrataRecordResponse(BaseModel):
    message: str

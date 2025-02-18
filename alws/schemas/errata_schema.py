import datetime
import re
from typing import Any, List, Optional

from pydantic import BaseModel, field_validator, computed_field

from alws.constants import ErrataReleaseStatus, ErrataPackageStatus


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
    id: Optional[int] = None

    class Config:
        from_attributes = True


class BaseErrataPackage(BaseModel):
    name: str
    version: str
    release: str
    epoch: int
    arch: str
    reboot_suggested: bool
    build_id: Optional[int] = None

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
    # TODO: freezed is no longer in use, see the note in models.py
    # Needs to be removed as part of BS-376
    freezed: Optional[bool] = False
    platform_id: int
    issued_date: datetime.date
    updated_date: datetime.date
    title: str
    description: str
    module: Optional[str] = None
    devel_module: Optional[bool] = False
    status: Optional[str] = "final"
    version: Optional[str] = "3"
    severity: str
    rights: Optional[str] = None
    definition_id: Optional[str] = None
    definition_version: Optional[str] = "635"
    definition_class: Optional[str] = "patch"
    affected_cpe: Optional[List[str]] = None
    criteria: Optional[Any] = None
    tests: Optional[Any] = None
    objects: Optional[Any] = None
    states: Optional[Any] = None
    variables: Optional[Any] = None
    references: List[BaseErrataReference]
    packages: List[BaseErrataPackage]

    @computed_field
    @property
    def is_issued_by_almalinux(self) -> bool:
        return bool(re.search(r"AL[BES]A-\d{4}:A", self.id))


class ErrataRecord(BaseErrataRecord):
    references: List[ErrataReference]
    packages: List[ErrataPackage]
    title: Optional[str] = None
    original_title: str
    description: Optional[str] = None
    issued_date: datetime.datetime
    updated_date: datetime.datetime
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
    updated_date: datetime.datetime
    platform_id: int


class CreateErrataResponse(BaseModel):
    ok: bool
    error: Optional[str] = None


class ChangeErrataPackageStatusResponse(BaseModel):
    ok: bool
    error: Optional[str] = None


class ChangeErrataPackageStatusRequest(BaseModel):
    errata_record_id: str
    errata_platform_id: int
    build_id: int
    source: str
    status: ErrataPackageStatus


class UpdateErrataRequest(BaseModel):
    errata_record_id: str
    errata_platform_id: int
    title: Optional[str] = None
    description: Optional[str] = None


class ReleaseErrataRecordResponse(BaseModel):
    message: str

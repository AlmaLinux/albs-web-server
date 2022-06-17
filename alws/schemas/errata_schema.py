import datetime
from typing import List, Any, Optional

from pydantic import BaseModel, validator

from alws.models import ErrataPackageStatus


class BaseErrataCVE(BaseModel):
    id: str
    cvss3: str
    cwe: Optional[str] = None
    impact: str
    public: str

    class Config:
        orm_mode = True


class BaseErrataReference(BaseModel):
    href: str
    ref_id: str
    ref_type: str
    title: Optional[str] = None
    cve: Optional[BaseErrataCVE] = None

    @validator('ref_type', pre=True)
    def validator_ref_type(cls, value):
        return str(value)


class ErrataReference(BaseErrataReference):
    id: int

    class Config:
        orm_mode = True
    

class BaseErrataPackage(BaseModel):
    name: str
    version: str
    release: str
    epoch: int
    arch: str
    reboot_suggested: bool

    class Config:
        orm_mode = True


class AlbsPackage(BaseModel):
    id: int
    albs_artifact_id: Optional[int]
    build_id: Optional[int]
    task_id: Optional[int]
    name: Optional[str]
    status: str

    @validator('status', pre=True)
    def status_validator(cls, status):
        return status.value

    class Config:
        orm_mode = True


class ErrataPackage(BaseErrataPackage):
    id: int
    source_srpm: Optional[str]
    albs_packages: List[AlbsPackage]
    
    class Config:
        orm_mode = True


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
    title: Optional[str]
    original_title: str
    description: Optional[str]
    original_description: str

    class Config:
        orm_mode = True


class ErrataListResponse(BaseModel):
    records: List[ErrataRecord]
    total_records: Optional[int]
    current_page: Optional[int]


class CompactErrataRecord(BaseModel):
    id: str
    updated_date: datetime.date


class CreateErrataResponse(BaseModel):
    ok: bool


class ChangeErrataPackageStatusResponse(BaseModel):
    ok: bool
    error: Optional[str]


class ChangeErrataPackageStatusRequest(BaseModel):
    errata_record_id: str
    build_id: int
    source: str
    status: ErrataPackageStatus


class UpdateErrataRequest(BaseModel):
    errata_record_id: str
    title: Optional[str]
    description: Optional[str]
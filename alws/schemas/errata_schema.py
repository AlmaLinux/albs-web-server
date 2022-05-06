import datetime
from typing import List, Any, Optional

from pydantic import BaseModel


class BaseErrataCVE(BaseModel):
    id: str
    cvss3: str
    cwe: str
    impact: str
    public: str     # TODO: public is actually a date

    class Config:
        orm_mode = True


class BaseErrataReference(BaseModel):
    href: str
    ref_id: str
    title: Optional[str] = None # TODO
    cves: Optional[List[BaseErrataCVE]] = []


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
    # reboot_suggested: bool # TODO

    class Config:
        orm_mode = True


class ErrataPackage(BaseErrataPackage):
    id: int
    
    class Config:
        orm_mode = True


class BaseErrataRecord(BaseModel):
    id: str
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
    criteria: Any    # TODO
    tests: Any       # TODO
    objects: Any     # TODO
    states: Any      # TODO
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
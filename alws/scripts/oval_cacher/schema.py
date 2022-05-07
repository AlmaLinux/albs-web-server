from __future__ import annotations

from typing import List, Optional
import datetime

from pydantic import BaseModel, Field, validator


class OvalGenericInfo(BaseModel):
    RHSA: str
    severity: str
    released_on: str
    CVEs: List[str]
    bugzillas: List[str]
    resource_url: str


class Generator(BaseModel):
    oval_product_name: str = Field(..., alias="oval:product_name")
    oval_schema_version: str = Field(..., alias="oval:schema_version")
    oval_timestamp: str = Field(..., alias="oval:timestamp")


class Affected(BaseModel):
    platform: List[str]
    family: str

    @validator("platform", pre=True)
    def validator_platform(cls, value):
        if isinstance(value, str):
            return [value]
        return value


class Reference(BaseModel):
    source: str
    ref_id: str
    ref_url: str


class Issued(BaseModel):
    date: datetime.date


class Updated(BaseModel):
    date: datetime.date


class Bugzilla(BaseModel):
    description: str
    id: str
    href: str


class Advisory(BaseModel):
    severity: str
    rights: str
    issued: Issued
    updated: Updated
    cve: Optional[List[str]] = None
    bugzilla: Optional[List[Bugzilla]] = []
    affected_cpe_list: List[str]
    from_: str = Field(..., alias="from")

    @validator("affected_cpe_list", pre=True)
    def validator_cpe_list(cls, value):
        if isinstance(value, str):
            return [value]
        return value

    @validator("bugzilla", pre=True)
    def validator_bugzilla(cls, value):
        if isinstance(value, str):
            return [value]
        return value


class Metadata(BaseModel):
    title: str
    affected: Affected
    reference: List[Reference]
    description: str
    advisory: Advisory


class Criterion(BaseModel):
    test_ref: str
    comment: str


class Criteria(BaseModel):
    criterion: Optional[List[Criterion]] = None
    criteria: Optional[List["Criteria"]] = None
    operator: Optional[str] = None

    @validator("criteria", pre=True)
    def validator_criteria(cls, value):
        if isinstance(value, dict):
            return [value]
        return value

    @validator("criterion", pre=True)
    def validator_criterion(cls, value):
        if isinstance(value, dict):
            return [value]
        return value


class Definition(BaseModel):
    metadata: Metadata
    criteria: Criteria
    id: str
    version: str
    class_: str = Field(..., alias="class")


class Object(BaseModel):
    object_ref: str


class State(BaseModel):
    state_ref: str


class RpminfoTest(BaseModel):
    object: Object
    state: Optional[State] = None
    id: str
    version: str
    comment: str
    check: str


class RpminfoObject(BaseModel):
    name: str
    id: str
    version: str


class RpminfoState(BaseModel):
    id: str
    version: str
    evr: Optional[str] = None
    arch: Optional[str] = None
    signature_keyid: Optional[str] = None


class OvalDefinition(BaseModel):
    generator: Generator
    definition: Optional[Definition] = None
    tests: Optional[List[RpminfoTest]] = None
    objects: Optional[List[RpminfoObject]] = None
    states: Optional[List[RpminfoState]] = None


class Cvss3(BaseModel):
    cvss3_base_score: str
    cvss3_scoring_vector: str
    status: str


class AffectedReleaseItem(BaseModel):
    product_name: str
    release_date: str
    advisory: str
    cpe: str
    package: Optional[str]


class PackageStateItem(BaseModel):
    product_name: str
    fix_state: str
    package_name: str
    cpe: str


class CVEBugzilla(BaseModel):
    description: str
    id: str
    url: str


class CVE(BaseModel):
    threat_severity: Optional[str] = None
    public_date: str
    bugzilla: CVEBugzilla
    cvss3: Optional[Cvss3] = None
    cwe: Optional[str] = None
    details: List[str]
    statement: Optional[str] = None
    affected_release: List[AffectedReleaseItem]
    package_state: Optional[List[PackageStateItem]] = None
    upstream_fix: Optional[str] = None
    name: str
    csaw: bool


class CVRFReference(BaseModel):
    description: str
    type: str
    url: str


class DocumentReferences(BaseModel):
    reference: List[CVRFReference]


class Identification(BaseModel):
    id: str


class Revision(BaseModel):
    date: str
    number: str
    description: str


class RevisionHistory(BaseModel):
    revision: Revision


class Generator(BaseModel):
    date: str
    engine: str


class DocumentTracking(BaseModel):
    initial_release_date: str
    identification: Identification
    revision_history: RevisionHistory
    generator: Generator
    current_release_date: str
    version: str
    status: str


class FullProductName(BaseModel):
    product_id: str
    cpe: str
    product_name: str


class RelationshipItem(BaseModel):
    relates_to_product_reference: str
    product_reference: str
    full_product_name: FullProductName
    relation_type: str


class Branch(BaseModel):
    name: str
    type: str
    branch: Optional[List["Branch"]] = None
    full_product_name: Optional[FullProductName] = None


class ProductTree(BaseModel):
    relationship: List[RelationshipItem]
    branch: List[Branch]


class DocumentPublisher(BaseModel):
    issuing_authority: str
    contact_details: str
    type: str


class Notes(BaseModel):
    note: str


class ReferenceItem(BaseModel):
    description: str
    url: str


class References(BaseModel):
    reference: List[ReferenceItem]


class Involvement(BaseModel):
    party: str
    status: str


class Involvements(BaseModel):
    involvement: Involvement


class Status(BaseModel):
    product_id: List[str]
    type: str


class ProductStatuses(BaseModel):
    status: Status


class Remediation(BaseModel):
    description: str
    type: str
    url: str


class Remediations(BaseModel):
    remediation: Remediation


class Threat(BaseModel):
    description: str
    type: str


class Threats(BaseModel):
    threat: Threat


class VulnerabilityItem(BaseModel):
    notes: Notes
    cve: str
    references: References
    release_date: str
    involvements: Involvements
    product_statuses: ProductStatuses
    remediations: Remediations
    threats: Optional[Threats] = None
    discovery_date: str
    ordinal: str


class DocumentNotes(BaseModel):
    note: List[str]


class CVRF(BaseModel):
    document_title: str
    document_distribution: str
    document_references: DocumentReferences
    aggregate_severity: str
    document_tracking: DocumentTracking
    product_tree: ProductTree
    document_publisher: DocumentPublisher
    vulnerability: Optional[List[VulnerabilityItem]] = []
    document_notes: DocumentNotes
    document_type: str

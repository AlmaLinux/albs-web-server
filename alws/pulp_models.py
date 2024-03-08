import datetime
import uuid
from typing import Any, Dict, List, Optional

import sqlalchemy
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from alws.database import PulpBase


class UpdateRecord(PulpBase):
    __tablename__ = "rpm_updaterecord"

    content_ptr_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True
    )
    id: Mapped[str] = mapped_column(sqlalchemy.Text)
    issued_date: Mapped[str] = mapped_column(sqlalchemy.Text)
    updated_date: Mapped[str] = mapped_column(sqlalchemy.Text)
    description: Mapped[str] = mapped_column(sqlalchemy.Text)
    fromstr: Mapped[str] = mapped_column(sqlalchemy.Text)
    status: Mapped[str] = mapped_column(sqlalchemy.Text)
    title: Mapped[str] = mapped_column(sqlalchemy.Text)
    summary: Mapped[str] = mapped_column(sqlalchemy.Text)
    version: Mapped[str] = mapped_column(sqlalchemy.Text)
    type: Mapped[str] = mapped_column(sqlalchemy.Text)
    severity: Mapped[str] = mapped_column(sqlalchemy.Text)
    solution: Mapped[str] = mapped_column(sqlalchemy.Text)
    release: Mapped[str] = mapped_column(sqlalchemy.Text)
    rights: Mapped[str] = mapped_column(sqlalchemy.Text)
    pushcount: Mapped[str] = mapped_column(sqlalchemy.Text)
    digest: Mapped[str] = mapped_column(sqlalchemy.Text)
    reboot_suggested: Mapped[bool] = mapped_column(sqlalchemy.Boolean)

    collections: Mapped[List["UpdateCollection"]] = relationship(
        "UpdateCollection"
    )
    references: Mapped[List["UpdateReference"]] = relationship(
        "UpdateReference"
    )


class UpdateCollection(PulpBase):
    __tablename__ = "rpm_updatecollection"

    pulp_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True
    )
    pulp_created: Mapped[datetime.datetime] = mapped_column(
        sqlalchemy.DATETIME
    )
    pulp_last_updated: Mapped[datetime.datetime] = mapped_column(
        sqlalchemy.DATETIME
    )

    name: Mapped[str] = mapped_column(sqlalchemy.Text)
    shortname: Mapped[str] = mapped_column(sqlalchemy.Text)
    module: Mapped[Optional[Dict[str, Any]]] = mapped_column(
        sqlalchemy.JSON, nullable=True
    )

    update_record_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        sqlalchemy.ForeignKey(UpdateRecord.content_ptr_id),
        nullable=False,
    )
    packages: Mapped[List["UpdatePackage"]] = relationship("UpdatePackage")


class UpdatePackage(PulpBase):
    __tablename__ = "rpm_updatecollectionpackage"

    pulp_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    pulp_created: Mapped[datetime.datetime] = mapped_column(
        sqlalchemy.DATETIME, default=datetime.datetime.now
    )
    pulp_last_updated: Mapped[datetime.datetime] = mapped_column(
        sqlalchemy.DATETIME,
        default=datetime.datetime.now,
    )
    arch: Mapped[str] = mapped_column(sqlalchemy.Text)
    filename: Mapped[str] = mapped_column(sqlalchemy.Text)
    name: Mapped[str] = mapped_column(sqlalchemy.Text)
    version: Mapped[str] = mapped_column(sqlalchemy.Text)
    release: Mapped[str] = mapped_column(sqlalchemy.Text)
    epoch: Mapped[str] = mapped_column(sqlalchemy.Text)
    reboot_suggested: Mapped[bool] = mapped_column(
        sqlalchemy.Boolean, default=False
    )
    relogin_suggested: Mapped[bool] = mapped_column(
        sqlalchemy.Boolean, default=False
    )
    restart_suggested: Mapped[bool] = mapped_column(
        sqlalchemy.Boolean, default=False
    )
    src: Mapped[str] = mapped_column(sqlalchemy.Text)
    sum: Mapped[str] = mapped_column(sqlalchemy.Text)
    update_collection_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        sqlalchemy.ForeignKey(UpdateCollection.pulp_id),
        nullable=False,
    )
    sum_type: Mapped[int] = mapped_column(sqlalchemy.Integer)


class UpdateReference(PulpBase):
    __tablename__ = "rpm_updatereference"

    pulp_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    pulp_created: Mapped[datetime.datetime] = mapped_column(
        sqlalchemy.DATETIME, default=datetime.datetime.now
    )
    pulp_last_updated: Mapped[datetime.datetime] = mapped_column(
        sqlalchemy.DATETIME,
        default=datetime.datetime.now,
    )
    href: Mapped[str] = mapped_column(sqlalchemy.Text)
    ref_id: Mapped[Optional[str]] = mapped_column(
        sqlalchemy.Text, nullable=True
    )
    title: Mapped[Optional[str]] = mapped_column(
        sqlalchemy.Text, nullable=True
    )
    ref_type: Mapped[str] = mapped_column(sqlalchemy.Text)
    update_record_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        sqlalchemy.ForeignKey(UpdateRecord.content_ptr_id),
        nullable=False,
    )


class CoreRepository(PulpBase):
    __tablename__ = "core_repository"

    pulp_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    pulp_created: Mapped[datetime.datetime] = mapped_column(
        sqlalchemy.DATETIME, default=datetime.datetime.now
    )
    pulp_last_updated: Mapped[datetime.datetime] = mapped_column(
        sqlalchemy.DATETIME,
        default=datetime.datetime.now,
    )
    name: Mapped[str] = mapped_column(sqlalchemy.Text)
    description: Mapped[Optional[str]] = mapped_column(
        sqlalchemy.Text, nullable=True
    )
    next_version: Mapped[int] = mapped_column(sqlalchemy.Integer)
    pulp_type: Mapped[str] = mapped_column(sqlalchemy.Text)
    remote_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), nullable=True
    )
    retain_repo_versions: Mapped[Optional[int]] = mapped_column(
        sqlalchemy.Integer, nullable=True
    )
    user_hidden: Mapped[bool] = mapped_column(sqlalchemy.Boolean)

    repository_content: Mapped["CoreRepositoryContent"] = relationship(
        "CoreRepositoryContent",
        back_populates="repository",
    )
    versions: Mapped[List["CoreRepositoryVersion"]] = relationship(
        "CoreRepositoryVersion",
        back_populates="repository",
    )


class CoreRepositoryVersion(PulpBase):
    __tablename__ = "core_repositoryversion"

    pulp_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    pulp_created: Mapped[datetime.datetime] = mapped_column(
        sqlalchemy.DATETIME, default=datetime.datetime.now
    )
    pulp_last_updated: Mapped[datetime.datetime] = mapped_column(
        sqlalchemy.DATETIME,
        default=datetime.datetime.now,
    )
    number: Mapped[int] = mapped_column(sqlalchemy.Integer)
    complete: Mapped[bool] = mapped_column(sqlalchemy.Boolean)
    base_version_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), nullable=True
    )
    repository_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        sqlalchemy.ForeignKey(CoreRepository.pulp_id),
    )
    info: Mapped[Dict[str, Any]] = mapped_column(JSONB)

    repository: Mapped[CoreRepository] = relationship(
        CoreRepository,
        back_populates="versions",
    )


class CoreContent(PulpBase):
    __tablename__ = "core_content"

    pulp_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    pulp_created: Mapped[datetime.datetime] = mapped_column(
        sqlalchemy.DATETIME, default=datetime.datetime.now
    )
    pulp_last_updated: Mapped[datetime.datetime] = mapped_column(
        sqlalchemy.DATETIME,
        default=datetime.datetime.now,
    )
    pulp_type: Mapped[str] = mapped_column(sqlalchemy.Text)
    upstream_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        nullable=True,
    )
    timestamp_of_interest: Mapped[datetime.datetime] = mapped_column(
        sqlalchemy.DATETIME,
        default=datetime.datetime.now,
    )
    rpm_package: Mapped["RpmPackage"] = relationship(
        "RpmPackage",
        back_populates="content",
    )
    core_contentartifact: Mapped[List["CoreContentArtifact"]] = relationship(
        "CoreContentArtifact",
        back_populates="content",
    )
    core_repositorycontent: Mapped["CoreRepositoryContent"] = relationship(
        "CoreRepositoryContent",
        back_populates="content",
    )

    @property
    def file_href(self):
        return f"/pulp/api/v3/content/file/files/{self.pulp_id}/"


class CoreContentArtifact(PulpBase):
    __tablename__ = "core_contentartifact"

    pulp_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    pulp_created: Mapped[datetime.datetime] = mapped_column(
        sqlalchemy.DATETIME, default=datetime.datetime.now
    )
    pulp_last_updated: Mapped[Optional[datetime.datetime]] = mapped_column(
        sqlalchemy.DATETIME,
        default=datetime.datetime.now,
        nullable=True,
    )
    relative_path: Mapped[Optional[uuid.UUID]] = mapped_column(sqlalchemy.Text)
    artifact_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        sqlalchemy.ForeignKey("core_artifact.pulp_id"),
        nullable=True,
    )
    content_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        sqlalchemy.ForeignKey(CoreContent.pulp_id),
    )
    artifact: Mapped["CoreArtifact"] = relationship(
        "CoreArtifact",
        foreign_keys=[artifact_id],
        back_populates="core_contentartifact",
    )
    content: Mapped[CoreContent] = relationship(
        CoreContent,
        foreign_keys=[content_id],
        back_populates="core_contentartifact",
    )


class CoreArtifact(PulpBase):
    __tablename__ = "core_artifact"

    pulp_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    pulp_created: Mapped[datetime.datetime] = mapped_column(
        sqlalchemy.DATETIME, default=datetime.datetime.now
    )
    pulp_last_updated: Mapped[Optional[datetime.datetime]] = mapped_column(
        sqlalchemy.DATETIME,
        default=datetime.datetime.now,
        nullable=True,
    )
    file: Mapped[str] = mapped_column(sqlalchemy.VARCHAR(255))
    size: Mapped[int] = mapped_column(sqlalchemy.BigInteger)
    md5: Mapped[Optional[str]] = mapped_column(
        sqlalchemy.VARCHAR(32), nullable=True
    )
    sha1: Mapped[Optional[str]] = mapped_column(
        sqlalchemy.VARCHAR(40), nullable=True
    )
    sha224: Mapped[Optional[str]] = mapped_column(
        sqlalchemy.VARCHAR(56), nullable=True
    )
    sha256: Mapped[str] = mapped_column(sqlalchemy.VARCHAR(64))
    sha384: Mapped[Optional[str]] = mapped_column(
        sqlalchemy.VARCHAR(96), nullable=True
    )
    sha512: Mapped[Optional[str]] = mapped_column(
        sqlalchemy.VARCHAR(128), nullable=True
    )
    timestamp_of_interest: Mapped[datetime.datetime] = mapped_column(
        sqlalchemy.DATETIME,
        default=datetime.datetime.now,
    )
    core_contentartifact: Mapped[List[CoreContentArtifact]] = relationship(
        CoreContentArtifact,
        back_populates="artifact",
    )


class CoreRepositoryContent(PulpBase):
    __tablename__ = "core_repositorycontent"

    pulp_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    pulp_created: Mapped[datetime.datetime] = mapped_column(
        sqlalchemy.DATETIME, default=datetime.datetime.now
    )
    pulp_last_updated: Mapped[datetime.datetime] = mapped_column(
        sqlalchemy.DATETIME,
        default=datetime.datetime.now,
    )
    content_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        sqlalchemy.ForeignKey(CoreContent.pulp_id),
    )
    repository_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        sqlalchemy.ForeignKey(CoreRepository.pulp_id),
    )
    version_added_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        sqlalchemy.ForeignKey(CoreRepositoryVersion.pulp_id),
    )
    version_removed_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        sqlalchemy.ForeignKey(CoreRepositoryVersion.pulp_id),
        nullable=True,
    )

    content: Mapped[List[CoreContent]] = relationship(
        CoreContent,
        foreign_keys=[content_id],
        back_populates="core_repositorycontent",
    )
    repository: Mapped[List[CoreRepository]] = relationship(
        CoreRepository,
        foreign_keys=[repository_id],
        back_populates="repository_content",
    )
    added_version: Mapped[List[CoreRepositoryVersion]] = relationship(
        CoreRepositoryVersion,
        foreign_keys=[version_added_id],
    )
    removed_version: Mapped[List[CoreRepositoryVersion]] = relationship(
        CoreRepositoryVersion,
        foreign_keys=[version_removed_id],
    )


class RpmPackage(PulpBase):
    __tablename__ = "rpm_package"

    content_ptr_id = mapped_column(
        UUID(as_uuid=True),
        sqlalchemy.ForeignKey(CoreContent.pulp_id),
        primary_key=True,
    )
    name: Mapped[str] = mapped_column(sqlalchemy.VARCHAR(255))
    epoch: Mapped[str] = mapped_column(sqlalchemy.VARCHAR(10))
    version: Mapped[str] = mapped_column(sqlalchemy.VARCHAR(255))
    release: Mapped[str] = mapped_column(sqlalchemy.VARCHAR(255))
    arch: Mapped[str] = mapped_column(sqlalchemy.VARCHAR(20))
    pkgId: Mapped[str] = mapped_column(sqlalchemy.Text)
    checksum_type: Mapped[str] = mapped_column(sqlalchemy.Text)
    summary: Mapped[str] = mapped_column(sqlalchemy.Text)
    description: Mapped[str] = mapped_column(sqlalchemy.Text)
    url: Mapped[str] = mapped_column(sqlalchemy.Text)
    # changelogs = mapped_column(JSONB)
    # files = mapped_column(JSONB)
    # requires = mapped_column(JSONB)
    # provides = mapped_column(JSONB)
    # conflicts = mapped_column(JSONB)
    # obsoletes = mapped_column(JSONB)
    # suggests = mapped_column(JSONB)
    # enhances = mapped_column(JSONB)
    # recommends = mapped_column(JSONB)
    # supplements = mapped_column(JSONB)
    location_base: Mapped[str] = mapped_column(sqlalchemy.Text)
    location_href: Mapped[str] = mapped_column(sqlalchemy.Text)
    rpm_buildhost: Mapped[str] = mapped_column(sqlalchemy.Text)
    rpm_group: Mapped[str] = mapped_column(sqlalchemy.Text)
    rpm_license: Mapped[str] = mapped_column(sqlalchemy.Text)
    rpm_packager: Mapped[str] = mapped_column(sqlalchemy.Text)
    rpm_sourcerpm: Mapped[str] = mapped_column(sqlalchemy.Text)
    rpm_vendor: Mapped[str] = mapped_column(sqlalchemy.Text)
    rpm_header_start: Mapped[Optional[int]] = mapped_column(
        sqlalchemy.BigInteger, nullable=True
    )
    rpm_header_end: Mapped[Optional[int]] = mapped_column(
        sqlalchemy.BigInteger, nullable=True
    )
    is_modular: Mapped[bool] = mapped_column(sqlalchemy.Boolean)
    size_archive: Mapped[Optional[int]] = mapped_column(
        sqlalchemy.BigInteger, nullable=True
    )
    size_installed: Mapped[Optional[int]] = mapped_column(
        sqlalchemy.BigInteger, nullable=True
    )
    size_package: Mapped[Optional[int]] = mapped_column(
        sqlalchemy.BigInteger, nullable=True
    )
    time_build: Mapped[Optional[int]] = mapped_column(
        sqlalchemy.BigInteger, nullable=True
    )
    time_file: Mapped[Optional[int]] = mapped_column(
        sqlalchemy.BigInteger, nullable=True
    )

    content: Mapped[CoreContent] = relationship(
        CoreContent,
        back_populates="rpm_package",
    )

    @property
    def nevra(self) -> str:
        return f"{self.epoch}:{self.name}-{self.version}-{self.release}.{self.arch}"

    def __repr__(self) -> str:
        return f"RpmPackage <{self.content_ptr_id}>: {self.nevra}"

    @property
    def pulp_href(self) -> str:
        return f"/pulp/api/v3/content/rpm/packages/{str(self.content_ptr_id)}/"

    @property
    def repo_ids(self) -> List[uuid.UUID]:
        return [
            repo_content.repository_id
            for repo_content in self.content.core_repositorycontent
            if repo_content.version_removed_id is None
        ]

    @property
    def sha256(self) -> str:
        return self.content.core_contentartifact[0].artifact.sha256

    def as_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "epoch": self.epoch,
            "version": self.version,
            "release": self.release,
            "arch": self.arch,
        }


class RpmModulemd(PulpBase):
    __tablename__ = "rpm_modulemd"

    content_ptr_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        sqlalchemy.ForeignKey(CoreContent.pulp_id),
        primary_key=True,
    )
    name: Mapped[str] = mapped_column(sqlalchemy.Text)
    stream: Mapped[str] = mapped_column(sqlalchemy.Text)
    version: Mapped[str] = mapped_column(sqlalchemy.Text)
    context: Mapped[str] = mapped_column(sqlalchemy.Text)
    arch: Mapped[str] = mapped_column(sqlalchemy.Text)

    @property
    def nsvca(self):
        return f"{self.name}:{self.stream}:{self.version}:{self.context}:{self.arch}"


class RpmModulemdPackages(PulpBase):
    __tablename__ = "rpm_modulemd_packages"

    id: Mapped[int] = mapped_column(sqlalchemy.Integer, primary_key=True)
    modulemd_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        sqlalchemy.ForeignKey(RpmModulemd.content_ptr_id),
    )
    package_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        sqlalchemy.ForeignKey(RpmPackage.content_ptr_id),
    )

import uuid
from datetime import datetime
from typing import Any, Dict, List

import sqlalchemy
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import mapped_column, relationship

from alws.database import PulpBase


class UpdateRecord(PulpBase):
    __tablename__ = "rpm_updaterecord"

    content_ptr_id = mapped_column(UUID(as_uuid=True), primary_key=True)
    id = mapped_column(sqlalchemy.Text)
    issued_date = mapped_column(sqlalchemy.Text)
    updated_date = mapped_column(sqlalchemy.Text)
    description = mapped_column(sqlalchemy.Text)
    fromstr = mapped_column(sqlalchemy.Text)
    status = mapped_column(sqlalchemy.Text)
    title = mapped_column(sqlalchemy.Text)
    summary = mapped_column(sqlalchemy.Text)
    version = mapped_column(sqlalchemy.Text)
    type = mapped_column(sqlalchemy.Text)
    severity = mapped_column(sqlalchemy.Text)
    solution = mapped_column(sqlalchemy.Text)
    release = mapped_column(sqlalchemy.Text)
    rights = mapped_column(sqlalchemy.Text)
    pushcount = mapped_column(sqlalchemy.Text)
    digest = mapped_column(sqlalchemy.Text)
    reboot_suggested = mapped_column(sqlalchemy.Boolean)

    collections: List["UpdateCollection"] = relationship("UpdateCollection")
    references: List["UpdateReference"] = relationship("UpdateReference")


class UpdateCollection(PulpBase):
    __tablename__ = "rpm_updatecollection"

    pulp_id = mapped_column(UUID(as_uuid=True), primary_key=True)
    pulp_created = mapped_column(sqlalchemy.DATETIME)
    pulp_last_updated = mapped_column(sqlalchemy.DATETIME)

    name = mapped_column(sqlalchemy.Text)
    shortname = mapped_column(sqlalchemy.Text)
    module = mapped_column(sqlalchemy.JSON, nullable=True)

    update_record_id = mapped_column(
        UUID(as_uuid=True),
        sqlalchemy.ForeignKey(UpdateRecord.content_ptr_id),
        nullable=False,
    )
    packages: List["UpdatePackage"] = relationship("UpdatePackage")


class UpdatePackage(PulpBase):
    __tablename__ = "rpm_updatecollectionpackage"

    pulp_id = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    pulp_created = mapped_column(sqlalchemy.DATETIME, default=datetime.now)
    pulp_last_updated = mapped_column(
        sqlalchemy.DATETIME,
        default=datetime.now,
    )
    arch = mapped_column(sqlalchemy.Text)
    filename = mapped_column(sqlalchemy.Text)
    name = mapped_column(sqlalchemy.Text)
    version = mapped_column(sqlalchemy.Text)
    release = mapped_column(sqlalchemy.Text)
    epoch = mapped_column(sqlalchemy.Text)
    reboot_suggested = mapped_column(sqlalchemy.Boolean, default=False)
    relogin_suggested = mapped_column(sqlalchemy.Boolean, default=False)
    restart_suggested = mapped_column(sqlalchemy.Boolean, default=False)
    src = mapped_column(sqlalchemy.Text)
    sum = mapped_column(sqlalchemy.Text)
    update_collection_id = mapped_column(
        UUID(as_uuid=True),
        sqlalchemy.ForeignKey(UpdateCollection.pulp_id),
        nullable=False,
    )
    sum_type = mapped_column(sqlalchemy.Integer)


class UpdateReference(PulpBase):
    __tablename__ = "rpm_updatereference"

    pulp_id = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    pulp_created = mapped_column(sqlalchemy.DATETIME, default=datetime.now)
    pulp_last_updated = mapped_column(
        sqlalchemy.DATETIME,
        default=datetime.now,
    )
    href = mapped_column(sqlalchemy.Text)
    ref_id = mapped_column(sqlalchemy.Text, nullable=True)
    title = mapped_column(sqlalchemy.Text, nullable=True)
    ref_type = mapped_column(sqlalchemy.Text)
    update_record_id = mapped_column(
        UUID(as_uuid=True),
        sqlalchemy.ForeignKey(UpdateRecord.content_ptr_id),
        nullable=False,
    )


class CoreRepository(PulpBase):
    __tablename__ = "core_repository"

    pulp_id = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    pulp_created = mapped_column(sqlalchemy.DATETIME, default=datetime.now)
    pulp_last_updated = mapped_column(
        sqlalchemy.DATETIME,
        default=datetime.now,
    )
    name = mapped_column(sqlalchemy.Text)
    description = mapped_column(sqlalchemy.Text, nullable=True)
    next_version = mapped_column(sqlalchemy.Integer)
    pulp_type = mapped_column(sqlalchemy.Text)
    remote_id = mapped_column(UUID(as_uuid=True), nullable=True)
    retain_repo_versions = mapped_column(sqlalchemy.Integer, nullable=True)
    user_hidden = mapped_column(sqlalchemy.Boolean)

    repository_content = relationship(
        "CoreRepositoryContent",
        back_populates="repository",
    )
    versions = relationship(
        "CoreRepositoryVersion",
        back_populates="repository",
    )


class CoreRepositoryVersion(PulpBase):
    __tablename__ = "core_repositoryversion"

    pulp_id = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    pulp_created = mapped_column(sqlalchemy.DATETIME, default=datetime.now)
    pulp_last_updated = mapped_column(
        sqlalchemy.DATETIME,
        default=datetime.now,
    )
    number = mapped_column(sqlalchemy.Integer)
    complete = mapped_column(sqlalchemy.Boolean)
    base_version_id = mapped_column(UUID(as_uuid=True), nullable=True)
    repository_id = mapped_column(
        UUID(as_uuid=True),
        sqlalchemy.ForeignKey(CoreRepository.pulp_id),
    )
    info = mapped_column(JSONB)

    repository = relationship(
        CoreRepository,
        back_populates="versions",
    )


class CoreContent(PulpBase):
    __tablename__ = "core_content"

    pulp_id = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    pulp_created = mapped_column(sqlalchemy.DATETIME, default=datetime.now)
    pulp_last_updated = mapped_column(
        sqlalchemy.DATETIME,
        default=datetime.now,
    )
    pulp_type = mapped_column(sqlalchemy.Text)
    upstream_id = mapped_column(
        UUID(as_uuid=True),
        nullable=True,
    )
    timestamp_of_interest = mapped_column(
        sqlalchemy.DATETIME,
        default=datetime.now,
    )
    rpm_package: "RpmPackage" = relationship(
        "RpmPackage",
        back_populates="content",
    )
    core_contentartifact: "CoreContentArtifact" = relationship(
        "CoreContentArtifact",
        back_populates="content",
    )
    core_repositorycontent: "CoreRepositoryContent" = relationship(
        "CoreRepositoryContent",
        back_populates="content",
    )

    @property
    def file_href(self):
        return f"/pulp/api/v3/content/file/files/{self.pulp_id}/"


class CoreContentArtifact(PulpBase):
    __tablename__ = "core_contentartifact"

    pulp_id = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    pulp_created = mapped_column(sqlalchemy.DATETIME, default=datetime.now)
    pulp_last_updated = mapped_column(
        sqlalchemy.DATETIME,
        default=datetime.now,
        nullable=True,
    )
    relative_path = mapped_column(sqlalchemy.Text)
    artifact_id = mapped_column(
        UUID(as_uuid=True),
        sqlalchemy.ForeignKey("core_artifact.pulp_id"),
        nullable=True,
    )
    content_id = mapped_column(
        UUID(as_uuid=True),
        sqlalchemy.ForeignKey(CoreContent.pulp_id),
    )
    artifact: "CoreArtifact" = relationship(
        "CoreArtifact",
        foreign_keys=[artifact_id],
        back_populates="core_contentartifact",
    )
    content: CoreContent = relationship(
        CoreContent,
        foreign_keys=[content_id],
        back_populates="core_contentartifact",
    )


class CoreArtifact(PulpBase):
    __tablename__ = "core_artifact"

    pulp_id = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    pulp_created = mapped_column(sqlalchemy.DATETIME, default=datetime.now)
    pulp_last_updated = mapped_column(
        sqlalchemy.DATETIME,
        default=datetime.now,
        nullable=True,
    )
    file = mapped_column(sqlalchemy.VARCHAR(255))
    size = mapped_column(sqlalchemy.BigInteger)
    md5 = mapped_column(sqlalchemy.VARCHAR(32), nullable=True)
    sha1 = mapped_column(sqlalchemy.VARCHAR(40), nullable=True)
    sha224 = mapped_column(sqlalchemy.VARCHAR(56), nullable=True)
    sha256 = mapped_column(sqlalchemy.VARCHAR(64))
    sha384 = mapped_column(sqlalchemy.VARCHAR(96), nullable=True)
    sha512 = mapped_column(sqlalchemy.VARCHAR(128), nullable=True)
    timestamp_of_interest = mapped_column(
        sqlalchemy.DATETIME,
        default=datetime.now,
    )
    core_contentartifact: CoreContentArtifact = relationship(
        CoreContentArtifact,
        back_populates="artifact",
    )


class CoreRepositoryContent(PulpBase):
    __tablename__ = "core_repositorycontent"

    pulp_id = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    pulp_created = mapped_column(sqlalchemy.DATETIME, default=datetime.now)
    pulp_last_updated = mapped_column(
        sqlalchemy.DATETIME,
        default=datetime.now,
    )
    content_id = mapped_column(
        UUID(as_uuid=True),
        sqlalchemy.ForeignKey(CoreContent.pulp_id),
    )
    repository_id = mapped_column(
        UUID(as_uuid=True),
        sqlalchemy.ForeignKey(CoreRepository.pulp_id),
    )
    version_added_id = mapped_column(
        UUID(as_uuid=True),
        sqlalchemy.ForeignKey(CoreRepositoryVersion.pulp_id),
    )
    version_removed_id = mapped_column(
        UUID(as_uuid=True),
        sqlalchemy.ForeignKey(CoreRepositoryVersion.pulp_id),
        nullable=True,
    )

    content: List[CoreContent] = relationship(
        CoreContent,
        foreign_keys=[content_id],
        back_populates="core_repositorycontent",
    )
    repository: List[CoreRepository] = relationship(
        CoreRepository,
        foreign_keys=[repository_id],
        back_populates="repository_content",
    )
    added_version: List[CoreRepositoryVersion] = relationship(
        CoreRepositoryVersion,
        foreign_keys=[version_added_id],
    )
    removed_version: List[CoreRepositoryVersion] = relationship(
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
    name = mapped_column(sqlalchemy.VARCHAR(255))
    epoch = mapped_column(sqlalchemy.VARCHAR(10))
    version = mapped_column(sqlalchemy.VARCHAR(255))
    release = mapped_column(sqlalchemy.VARCHAR(255))
    arch = mapped_column(sqlalchemy.VARCHAR(20))
    pkgId = mapped_column(sqlalchemy.Text)
    checksum_type = mapped_column(sqlalchemy.Text)
    summary = mapped_column(sqlalchemy.Text)
    description = mapped_column(sqlalchemy.Text)
    url = mapped_column(sqlalchemy.Text)
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
    location_base = mapped_column(sqlalchemy.Text)
    location_href = mapped_column(sqlalchemy.Text)
    rpm_buildhost = mapped_column(sqlalchemy.Text)
    rpm_group = mapped_column(sqlalchemy.Text)
    rpm_license = mapped_column(sqlalchemy.Text)
    rpm_packager = mapped_column(sqlalchemy.Text)
    rpm_sourcerpm = mapped_column(sqlalchemy.Text)
    rpm_vendor = mapped_column(sqlalchemy.Text)
    rpm_header_start = mapped_column(sqlalchemy.BigInteger, nullable=True)
    rpm_header_end = mapped_column(sqlalchemy.BigInteger, nullable=True)
    is_modular = mapped_column(sqlalchemy.Boolean)
    size_archive = mapped_column(sqlalchemy.BigInteger, nullable=True)
    size_installed = mapped_column(sqlalchemy.BigInteger, nullable=True)
    size_package = mapped_column(sqlalchemy.BigInteger, nullable=True)
    time_build = mapped_column(sqlalchemy.BigInteger, nullable=True)
    time_file = mapped_column(sqlalchemy.BigInteger, nullable=True)

    content: CoreContent = relationship(
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

    content_ptr_id = mapped_column(
        UUID(as_uuid=True),
        sqlalchemy.ForeignKey(CoreContent.pulp_id),
        primary_key=True,
    )
    name = mapped_column(sqlalchemy.Text)
    stream = mapped_column(sqlalchemy.Text)
    version = mapped_column(sqlalchemy.Text)
    context = mapped_column(sqlalchemy.Text)
    arch = mapped_column(sqlalchemy.Text)

    @property
    def nsvca(self):
        return f"{self.name}:{self.stream}:{self.version}:{self.context}:{self.arch}"


class RpmModulemdPackages(PulpBase):
    __tablename__ = "rpm_modulemd_packages"

    id = mapped_column(sqlalchemy.Integer, primary_key=True)
    modulemd_id = mapped_column(
        UUID(as_uuid=True),
        sqlalchemy.ForeignKey(RpmModulemd.content_ptr_id),
    )
    package_id = mapped_column(
        UUID(as_uuid=True),
        sqlalchemy.ForeignKey(RpmPackage.content_ptr_id),
    )

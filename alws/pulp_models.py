import uuid
from datetime import datetime
from typing import Any, Dict, List

import sqlalchemy
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import relationship

from alws.database import PulpBase


class UpdateRecord(PulpBase):
    __tablename__ = "rpm_updaterecord"

    content_ptr_id = sqlalchemy.Column(UUID(as_uuid=True), primary_key=True)
    id = sqlalchemy.Column(sqlalchemy.Text)
    issued_date = sqlalchemy.Column(sqlalchemy.Text)
    updated_date = sqlalchemy.Column(sqlalchemy.Text)
    description = sqlalchemy.Column(sqlalchemy.Text)
    fromstr = sqlalchemy.Column(sqlalchemy.Text)
    status = sqlalchemy.Column(sqlalchemy.Text)
    title = sqlalchemy.Column(sqlalchemy.Text)
    summary = sqlalchemy.Column(sqlalchemy.Text)
    version = sqlalchemy.Column(sqlalchemy.Text)
    type = sqlalchemy.Column(sqlalchemy.Text)
    severity = sqlalchemy.Column(sqlalchemy.Text)
    solution = sqlalchemy.Column(sqlalchemy.Text)
    release = sqlalchemy.Column(sqlalchemy.Text)
    rights = sqlalchemy.Column(sqlalchemy.Text)
    pushcount = sqlalchemy.Column(sqlalchemy.Text)
    digest = sqlalchemy.Column(sqlalchemy.Text)
    reboot_suggested = sqlalchemy.Column(sqlalchemy.Boolean)

    collections: List["UpdateCollection"] = relationship("UpdateCollection")
    references: List["UpdateReference"] = relationship("UpdateReference")


class UpdateCollection(PulpBase):
    __tablename__ = "rpm_updatecollection"

    pulp_id = sqlalchemy.Column(UUID(as_uuid=True), primary_key=True)
    pulp_created = sqlalchemy.Column(sqlalchemy.DATETIME)
    pulp_last_updated = sqlalchemy.Column(sqlalchemy.DATETIME)

    name = sqlalchemy.Column(sqlalchemy.Text)
    shortname = sqlalchemy.Column(sqlalchemy.Text)
    module = sqlalchemy.Column(sqlalchemy.JSON, nullable=True)

    update_record_id = sqlalchemy.Column(
        UUID(as_uuid=True),
        sqlalchemy.ForeignKey(UpdateRecord.content_ptr_id),
        nullable=False,
    )
    packages: List["UpdatePackage"] = relationship("UpdatePackage")


class UpdatePackage(PulpBase):
    __tablename__ = "rpm_updatecollectionpackage"

    pulp_id = sqlalchemy.Column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    pulp_created = sqlalchemy.Column(sqlalchemy.DATETIME, default=datetime.now)
    pulp_last_updated = sqlalchemy.Column(
        sqlalchemy.DATETIME,
        default=datetime.now,
    )
    arch = sqlalchemy.Column(sqlalchemy.Text)
    filename = sqlalchemy.Column(sqlalchemy.Text)
    name = sqlalchemy.Column(sqlalchemy.Text)
    version = sqlalchemy.Column(sqlalchemy.Text)
    release = sqlalchemy.Column(sqlalchemy.Text)
    epoch = sqlalchemy.Column(sqlalchemy.Text)
    reboot_suggested = sqlalchemy.Column(sqlalchemy.Boolean, default=False)
    relogin_suggested = sqlalchemy.Column(sqlalchemy.Boolean, default=False)
    restart_suggested = sqlalchemy.Column(sqlalchemy.Boolean, default=False)
    src = sqlalchemy.Column(sqlalchemy.Text)
    sum = sqlalchemy.Column(sqlalchemy.Text)
    update_collection_id = sqlalchemy.Column(
        UUID(as_uuid=True),
        sqlalchemy.ForeignKey(UpdateCollection.pulp_id),
        nullable=False,
    )
    sum_type = sqlalchemy.Column(sqlalchemy.Integer)


class UpdateReference(PulpBase):
    __tablename__ = "rpm_updatereference"

    pulp_id = sqlalchemy.Column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    pulp_created = sqlalchemy.Column(sqlalchemy.DATETIME, default=datetime.now)
    pulp_last_updated = sqlalchemy.Column(
        sqlalchemy.DATETIME,
        default=datetime.now,
    )
    href = sqlalchemy.Column(sqlalchemy.Text)
    ref_id = sqlalchemy.Column(sqlalchemy.Text, nullable=True)
    title = sqlalchemy.Column(sqlalchemy.Text, nullable=True)
    ref_type = sqlalchemy.Column(sqlalchemy.Text)
    update_record_id = sqlalchemy.Column(
        UUID(as_uuid=True),
        sqlalchemy.ForeignKey(UpdateRecord.content_ptr_id),
        nullable=False,
    )


class CoreRepository(PulpBase):
    __tablename__ = "core_repository"

    pulp_id = sqlalchemy.Column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    pulp_created = sqlalchemy.Column(sqlalchemy.DATETIME, default=datetime.now)
    pulp_last_updated = sqlalchemy.Column(
        sqlalchemy.DATETIME,
        default=datetime.now,
    )
    name = sqlalchemy.Column(sqlalchemy.Text)
    description = sqlalchemy.Column(sqlalchemy.Text, nullable=True)
    next_version = sqlalchemy.Column(sqlalchemy.Integer)
    pulp_type = sqlalchemy.Column(sqlalchemy.Text)
    remote_id = sqlalchemy.Column(UUID(as_uuid=True), nullable=True)
    retain_repo_versions = sqlalchemy.Column(sqlalchemy.Integer, nullable=True)
    user_hidden = sqlalchemy.Column(sqlalchemy.Boolean)

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

    pulp_id = sqlalchemy.Column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    pulp_created = sqlalchemy.Column(sqlalchemy.DATETIME, default=datetime.now)
    pulp_last_updated = sqlalchemy.Column(
        sqlalchemy.DATETIME,
        default=datetime.now,
    )
    number = sqlalchemy.Column(sqlalchemy.Integer)
    complete = sqlalchemy.Column(sqlalchemy.Boolean)
    base_version_id = sqlalchemy.Column(UUID(as_uuid=True), nullable=True)
    repository_id = sqlalchemy.Column(
        UUID(as_uuid=True),
        sqlalchemy.ForeignKey(CoreRepository.pulp_id),
    )
    info = sqlalchemy.Column(JSONB)

    repository = relationship(
        CoreRepository,
        back_populates="versions",
    )


class CoreContent(PulpBase):
    __tablename__ = "core_content"

    pulp_id = sqlalchemy.Column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    pulp_created = sqlalchemy.Column(sqlalchemy.DATETIME, default=datetime.now)
    pulp_last_updated = sqlalchemy.Column(
        sqlalchemy.DATETIME,
        default=datetime.now,
    )
    pulp_type = sqlalchemy.Column(sqlalchemy.Text)
    upstream_id = sqlalchemy.Column(
        UUID(as_uuid=True),
        nullable=True,
    )
    timestamp_of_interest = sqlalchemy.Column(
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

    pulp_id = sqlalchemy.Column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    pulp_created = sqlalchemy.Column(sqlalchemy.DATETIME, default=datetime.now)
    pulp_last_updated = sqlalchemy.Column(
        sqlalchemy.DATETIME,
        default=datetime.now,
        nullable=True,
    )
    relative_path = sqlalchemy.Column(sqlalchemy.Text)
    artifact_id = sqlalchemy.Column(
        UUID(as_uuid=True),
        sqlalchemy.ForeignKey("core_artifact.pulp_id"),
        nullable=True,
    )
    content_id = sqlalchemy.Column(
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

    pulp_id = sqlalchemy.Column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    pulp_created = sqlalchemy.Column(sqlalchemy.DATETIME, default=datetime.now)
    pulp_last_updated = sqlalchemy.Column(
        sqlalchemy.DATETIME,
        default=datetime.now,
        nullable=True,
    )
    file = sqlalchemy.Column(sqlalchemy.VARCHAR(255))
    size = sqlalchemy.Column(sqlalchemy.BigInteger)
    md5 = sqlalchemy.Column(sqlalchemy.VARCHAR(32), nullable=True)
    sha1 = sqlalchemy.Column(sqlalchemy.VARCHAR(40), nullable=True)
    sha224 = sqlalchemy.Column(sqlalchemy.VARCHAR(56), nullable=True)
    sha256 = sqlalchemy.Column(sqlalchemy.VARCHAR(64))
    sha384 = sqlalchemy.Column(sqlalchemy.VARCHAR(96), nullable=True)
    sha512 = sqlalchemy.Column(sqlalchemy.VARCHAR(128), nullable=True)
    timestamp_of_interest = sqlalchemy.Column(
        sqlalchemy.DATETIME,
        default=datetime.now,
    )
    core_contentartifact: CoreContentArtifact = relationship(
        CoreContentArtifact,
        back_populates="artifact",
    )


class CoreRepositoryContent(PulpBase):
    __tablename__ = "core_repositorycontent"

    pulp_id = sqlalchemy.Column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    pulp_created = sqlalchemy.Column(sqlalchemy.DATETIME, default=datetime.now)
    pulp_last_updated = sqlalchemy.Column(
        sqlalchemy.DATETIME,
        default=datetime.now,
    )
    content_id = sqlalchemy.Column(
        UUID(as_uuid=True),
        sqlalchemy.ForeignKey(CoreContent.pulp_id),
    )
    repository_id = sqlalchemy.Column(
        UUID(as_uuid=True),
        sqlalchemy.ForeignKey(CoreRepository.pulp_id),
    )
    version_added_id = sqlalchemy.Column(
        UUID(as_uuid=True),
        sqlalchemy.ForeignKey(CoreRepositoryVersion.pulp_id),
    )
    version_removed_id = sqlalchemy.Column(
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

    content_ptr_id = sqlalchemy.Column(
        UUID(as_uuid=True),
        sqlalchemy.ForeignKey(CoreContent.pulp_id),
        primary_key=True,
    )
    name = sqlalchemy.Column(sqlalchemy.VARCHAR(255))
    epoch = sqlalchemy.Column(sqlalchemy.VARCHAR(10))
    version = sqlalchemy.Column(sqlalchemy.VARCHAR(255))
    release = sqlalchemy.Column(sqlalchemy.VARCHAR(255))
    arch = sqlalchemy.Column(sqlalchemy.VARCHAR(20))
    pkgId = sqlalchemy.Column(sqlalchemy.Text)
    checksum_type = sqlalchemy.Column(sqlalchemy.Text)
    summary = sqlalchemy.Column(sqlalchemy.Text)
    description = sqlalchemy.Column(sqlalchemy.Text)
    url = sqlalchemy.Column(sqlalchemy.Text)
    # changelogs = sqlalchemy.Column(JSONB)
    # files = sqlalchemy.Column(JSONB)
    # requires = sqlalchemy.Column(JSONB)
    # provides = sqlalchemy.Column(JSONB)
    # conflicts = sqlalchemy.Column(JSONB)
    # obsoletes = sqlalchemy.Column(JSONB)
    # suggests = sqlalchemy.Column(JSONB)
    # enhances = sqlalchemy.Column(JSONB)
    # recommends = sqlalchemy.Column(JSONB)
    # supplements = sqlalchemy.Column(JSONB)
    location_base = sqlalchemy.Column(sqlalchemy.Text)
    location_href = sqlalchemy.Column(sqlalchemy.Text)
    rpm_buildhost = sqlalchemy.Column(sqlalchemy.Text)
    rpm_group = sqlalchemy.Column(sqlalchemy.Text)
    rpm_license = sqlalchemy.Column(sqlalchemy.Text)
    rpm_packager = sqlalchemy.Column(sqlalchemy.Text)
    rpm_sourcerpm = sqlalchemy.Column(sqlalchemy.Text)
    rpm_vendor = sqlalchemy.Column(sqlalchemy.Text)
    rpm_header_start = sqlalchemy.Column(sqlalchemy.BigInteger, nullable=True)
    rpm_header_end = sqlalchemy.Column(sqlalchemy.BigInteger, nullable=True)
    is_modular = sqlalchemy.Column(sqlalchemy.Boolean)
    size_archive = sqlalchemy.Column(sqlalchemy.BigInteger, nullable=True)
    size_installed = sqlalchemy.Column(sqlalchemy.BigInteger, nullable=True)
    size_package = sqlalchemy.Column(sqlalchemy.BigInteger, nullable=True)
    time_build = sqlalchemy.Column(sqlalchemy.BigInteger, nullable=True)
    time_file = sqlalchemy.Column(sqlalchemy.BigInteger, nullable=True)

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

    content_ptr_id = sqlalchemy.Column(
        UUID(as_uuid=True),
        sqlalchemy.ForeignKey(CoreContent.pulp_id),
        primary_key=True,
    )
    name = sqlalchemy.Column(sqlalchemy.Text)
    stream = sqlalchemy.Column(sqlalchemy.Text)
    version = sqlalchemy.Column(sqlalchemy.Text)
    context = sqlalchemy.Column(sqlalchemy.Text)
    arch = sqlalchemy.Column(sqlalchemy.Text)
    dependencies = sqlalchemy.Column(JSONB)
    artifacts = sqlalchemy.Column(JSONB)
    static_context = sqlalchemy.Column(sqlalchemy.Boolean)

    @property
    def nsvca(self):
        return f"{self.name}:{self.stream}:{self.version}:{self.context}:{self.arch}"


class RpmModulemdPackages(PulpBase):
    __tablename__ = "rpm_modulemd_packages"

    id = sqlalchemy.Column(sqlalchemy.Integer, primary_key=True)
    modulemd_id = sqlalchemy.Column(
        UUID(as_uuid=True),
        sqlalchemy.ForeignKey(RpmModulemd.content_ptr_id),
    )
    package_id = sqlalchemy.Column(
        UUID(as_uuid=True),
        sqlalchemy.ForeignKey(RpmPackage.content_ptr_id),
    )

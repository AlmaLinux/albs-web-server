import asyncio
import datetime
import re
from typing import Any, Dict, List, Literal, Optional

import sqlalchemy
from fastapi_users.db import (
    SQLAlchemyBaseOAuthAccountTable,
    SQLAlchemyBaseUserTable,
)
from fastapi_users_db_sqlalchemy.access_token import (
    SQLAlchemyBaseAccessTokenTable,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.associationproxy import (
    AssociationProxy,
    association_proxy,
)
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.orm import (
    Mapped,
    declarative_mixin,
    declared_attr,
    mapped_column,
    relationship,
)
from sqlalchemy.sql import func

from alws.config import settings
from alws.constants import (
    ErrataPackageStatus,
    ErrataReferenceType,
    ErrataReleaseStatus,
    GenKeyStatus,
    Permissions,
    PermissionTriad,
    ReleaseStatus,
    SignStatus,
)
from alws.database import Base

__all__ = [
    "Build",
    "BuildTask",
    "ErrataRecord",
    "NewErrataRecord",
    "Platform",
    "SignKey",
    "SignTask",
    "User",
    "UserAccessToken",
    "UserAction",
    "UserOauthAccount",
    "UserRole",
    "Team",
    "TestRepository",
]


@declarative_mixin
class TeamMixin:
    @declared_attr
    def team_id(cls) -> Mapped[Optional[int]]:
        # FIXME: Change nullable to False after owner population
        return mapped_column(
            sqlalchemy.Integer,
            sqlalchemy.ForeignKey(
                "teams.id",
                name=f"{cls.__tablename__}_team_id_fkey",
            ),
            nullable=True,
        )

    @declared_attr
    def team(cls) -> Mapped["Team"]:
        return relationship("Team")


@declarative_mixin
class PermissionsMixin:
    @declared_attr
    def owner_id(cls) -> Mapped[Optional[int]]:
        # FIXME: Change nullable to False after owner population
        return mapped_column(
            sqlalchemy.Integer,
            sqlalchemy.ForeignKey(
                "users.id",
                name=f"{cls.__tablename__}_owner_id_fkey",
            ),
            nullable=True,
        )

    @declared_attr
    def owner(cls) -> Mapped["User"]:
        return relationship("User")

    permissions: Mapped[int] = mapped_column(
        sqlalchemy.Integer, nullable=False, default=764
    )

    @property
    def permissions_triad(self):
        self.validate_permissions(self.permissions)
        perms_str = str(self.permissions)
        owner = int(perms_str[0])
        group = int(perms_str[1])
        other = int(perms_str[2])
        return PermissionTriad(
            Permissions(owner),
            Permissions(group),
            Permissions(other),
        )

    @staticmethod
    def validate_permissions(permissions: int):
        if len(str(permissions)) != 3:
            raise ValueError(
                "Incorrect permissions set, should be a string of 3 digits"
            )
        test = permissions
        while test > 0:
            # We check that each digit in permissions
            # isn't greater than 7 (octal numbers).
            # This way we ensure our permissions will be correct.
            if test % 10 > 7:
                raise ValueError("Incorrect permissions representation")
            test //= 10
        return permissions


@declarative_mixin
class TimeMixin:
    @declared_attr
    def started_at(cls) -> Mapped[Optional[datetime.datetime]]:
        return mapped_column(sqlalchemy.DateTime, nullable=True)

    @declared_attr
    def finished_at(cls) -> Mapped[Optional[datetime.datetime]]:
        return mapped_column(sqlalchemy.DateTime, nullable=True)


PlatformRepo = sqlalchemy.Table(
    "platform_repository",
    Base.metadata,
    sqlalchemy.Column(
        "platform_id",
        sqlalchemy.Integer,
        sqlalchemy.ForeignKey("platforms.id"),
        primary_key=True,
    ),
    sqlalchemy.Column(
        "repository_id",
        sqlalchemy.Integer,
        sqlalchemy.ForeignKey("repositories.id"),
        primary_key=True,
    ),
)

FlavourRepo = sqlalchemy.Table(
    "platform_flavour_repository",
    Base.metadata,
    sqlalchemy.Column(
        "flavour_id",
        sqlalchemy.Integer,
        sqlalchemy.ForeignKey("platform_flavours.id"),
        primary_key=True,
    ),
    sqlalchemy.Column(
        "repository_id",
        sqlalchemy.Integer,
        sqlalchemy.ForeignKey("repositories.id"),
        primary_key=True,
    ),
)

BuildPlatformFlavour = sqlalchemy.Table(
    "build_platform_flavour",
    Base.metadata,
    sqlalchemy.Column(
        "flavour_id",
        sqlalchemy.Integer,
        sqlalchemy.ForeignKey("platform_flavours.id"),
        primary_key=True,
    ),
    sqlalchemy.Column(
        "build_id",
        sqlalchemy.Integer,
        sqlalchemy.ForeignKey("builds.id"),
        primary_key=True,
    ),
)

ReferencePlatforms = sqlalchemy.Table(
    "reference_platforms",
    Base.metadata,
    sqlalchemy.Column(
        "platform_id",
        sqlalchemy.Integer,
        sqlalchemy.ForeignKey("platforms.id"),
        primary_key=True,
    ),
    sqlalchemy.Column(
        "refefence_platform_id",
        sqlalchemy.Integer,
        sqlalchemy.ForeignKey("platforms.id"),
        primary_key=True,
    ),
)

PlatformRoleMapping = sqlalchemy.Table(
    "platform_role_mapping",
    Base.metadata,
    sqlalchemy.Column(
        "platform_id",
        sqlalchemy.Integer,
        sqlalchemy.ForeignKey(
            "platforms.id",
            name="platform_role_mapping_platform_id_fkey",
        ),
        primary_key=True,
    ),
    sqlalchemy.Column(
        "role_id",
        sqlalchemy.Integer,
        sqlalchemy.ForeignKey(
            "user_roles.id",
            name="platform_role_mapping_user_id_fkey",
        ),
        primary_key=True,
    ),
)


class Platform(PermissionsMixin, Base):
    __tablename__ = "platforms"

    id: Mapped[int] = mapped_column(sqlalchemy.Integer, primary_key=True)
    contact_mail: Mapped[Optional[str]] = mapped_column(
        sqlalchemy.Text, nullable=True
    )
    copyright: Mapped[Optional[str]] = mapped_column(
        sqlalchemy.Text, nullable=True
    )
    type: Mapped[str] = mapped_column(sqlalchemy.Text, nullable=False)
    distr_type: Mapped[str] = mapped_column(sqlalchemy.Text, nullable=False)
    distr_version: Mapped[str] = mapped_column(sqlalchemy.Text, nullable=False)
    module_build_index: Mapped[int] = mapped_column(
        sqlalchemy.Integer, default=1
    )
    modularity: Mapped[Optional[Dict[str, Any]]] = mapped_column(
        JSONB, nullable=True
    )
    test_dist_name: Mapped[str] = mapped_column(sqlalchemy.Text, nullable=False)
    name: Mapped[str] = mapped_column(
        sqlalchemy.Text, nullable=False, unique=True, index=True
    )
    priority: Mapped[Optional[str]] = mapped_column(
        sqlalchemy.Integer, nullable=True
    )
    arch_list: Mapped[List[Dict[str, Any]]] = mapped_column(
        JSONB, nullable=False
    )
    copy_priority_arches: Mapped[List[Optional[Dict[str, Any]]]] = (
        mapped_column(JSONB, nullable=True)
    )
    weak_arch_list: Mapped[Optional[List[Dict[str, any]]]] = mapped_column(
        JSONB, nullable=True
    )
    data: Mapped[Dict[str, Any]] = mapped_column(JSONB, nullable=False)
    is_reference: Mapped[Optional[bool]] = mapped_column(
        sqlalchemy.Boolean, default=False, nullable=True
    )
    reference_platforms: Mapped[List["Platform"]] = relationship(
        "Platform",
        secondary=ReferencePlatforms,
        primaryjoin=(ReferencePlatforms.c.platform_id == id),
        secondaryjoin=(ReferencePlatforms.c.refefence_platform_id == id),
    )
    repos: Mapped[List["Repository"]] = relationship(
        "Repository", secondary=PlatformRepo
    )
    sign_keys: Mapped[List["SignKey"]] = relationship(
        "SignKey", back_populates="platform"
    )
    roles: Mapped[List["UserRole"]] = relationship(
        "UserRole", secondary=PlatformRoleMapping
    )


class CustomRepoRepr(Base):
    __abstract__ = True

    def __repr__(self):
        return f"{self.__class__.__name__}: {self.name} {self.arch} {self.url}"


class Repository(CustomRepoRepr, PermissionsMixin):
    __tablename__ = "repositories"
    __table_args__ = (
        sqlalchemy.UniqueConstraint(
            "name",
            "arch",
            "type",
            "debug",
            name="repos_uix",
        ),
    )

    id: Mapped[int] = mapped_column(sqlalchemy.Integer, primary_key=True)
    name: Mapped[str] = mapped_column(sqlalchemy.Text, nullable=False)
    arch: Mapped[str] = mapped_column(sqlalchemy.Text, nullable=False)
    url: Mapped[str] = mapped_column(sqlalchemy.Text, nullable=False)
    type: Mapped[str] = mapped_column(sqlalchemy.Text, nullable=False)
    debug: Mapped[bool] = mapped_column(sqlalchemy.Boolean, default=False)
    mock_enabled: Mapped[Optional[bool]] = mapped_column(
        sqlalchemy.Boolean,
        default=True,
        nullable=True,
    )
    production: Mapped[Optional[bool]] = mapped_column(
        sqlalchemy.Boolean, default=False, nullable=True
    )
    pulp_href: Mapped[Optional[str]] = mapped_column(sqlalchemy.Text)
    export_path: Mapped[Optional[str]] = mapped_column(
        sqlalchemy.Text, nullable=True
    )
    priority: Mapped[int] = mapped_column(
        sqlalchemy.Integer, default=10, nullable=False
    )
    platform_id: Mapped[Optional[int]] = mapped_column(
        sqlalchemy.Integer,
        sqlalchemy.ForeignKey("platforms.id"),
        nullable=True,
    )
    platform: Mapped["Platform"] = relationship("Platform")


class RepositoryRemote(CustomRepoRepr):
    __tablename__ = "repository_remotes"
    __tableargs__ = [
        sqlalchemy.UniqueConstraint(
            "name",
            "arch",
            "url",
            name="repo_remote_uix",
        ),
    ]

    id: Mapped[int] = mapped_column(sqlalchemy.Integer, primary_key=True)
    name: Mapped[str] = mapped_column(sqlalchemy.Text, nullable=False)
    arch: Mapped[str] = mapped_column(sqlalchemy.Text, nullable=False)
    url: Mapped[str] = mapped_column(sqlalchemy.Text, nullable=False)
    pulp_href: Mapped[str] = mapped_column(sqlalchemy.Text, nullable=False)


BuildRepo = sqlalchemy.Table(
    "build_repo",
    Base.metadata,
    sqlalchemy.Column(
        "build_id",
        sqlalchemy.Integer,
        sqlalchemy.ForeignKey("builds.id"),
        primary_key=True,
    ),
    sqlalchemy.Column(
        "repository_id",
        sqlalchemy.Integer,
        sqlalchemy.ForeignKey("repositories.id"),
        primary_key=True,
    ),
)

BuildDependency = sqlalchemy.Table(
    "build_dependency",
    Base.metadata,
    sqlalchemy.Column(
        "build_id",
        sqlalchemy.Integer,
        sqlalchemy.ForeignKey("builds.id"),
        primary_key=True,
    ),
    sqlalchemy.Column(
        "build_dependency",
        sqlalchemy.Integer,
        sqlalchemy.ForeignKey("builds.id"),
        primary_key=True,
    ),
)


class Build(PermissionsMixin, TeamMixin, Base):
    __tablename__ = "builds"

    id: Mapped[int] = mapped_column(sqlalchemy.Integer, primary_key=True)
    created_at: Mapped[datetime.datetime] = mapped_column(
        sqlalchemy.DateTime,
        nullable=False,
        default=func.current_timestamp(),
    )
    finished_at: Mapped[Optional[datetime.datetime]] = mapped_column(
        sqlalchemy.DateTime, nullable=True
    )
    tasks: Mapped[List["BuildTask"]] = relationship(
        "BuildTask", back_populates="build"
    )
    sign_tasks: Mapped[List["SignTask"]] = relationship(
        "SignTask",
        back_populates="build",
        order_by="SignTask.id",
    )
    repos: Mapped[List["Repository"]] = relationship(
        "Repository", secondary=BuildRepo
    )
    linked_builds: Mapped[List["Build"]] = relationship(
        "Build",
        secondary=BuildDependency,
        primaryjoin=(BuildDependency.c.build_id == id),
        secondaryjoin=(BuildDependency.c.build_dependency == id),
    )
    mock_options: Mapped[Dict[str, Any]] = mapped_column(JSONB)
    release_id: Mapped[Optional[int]] = mapped_column(
        sqlalchemy.Integer,
        sqlalchemy.ForeignKey(
            "build_releases.id",
            name="build_releases_id_fkey",
        ),
        nullable=True,
    )
    release: Mapped["Release"] = relationship("Release")
    source_rpms: Mapped[List["SourceRpm"]] = relationship(
        "SourceRpm", back_populates="build"
    )
    binary_rpms: Mapped[List["BinaryRpm"]] = relationship(
        "BinaryRpm", back_populates="build"
    )
    platform_flavors: Mapped[List["PlatformFlavour"]] = relationship(
        "PlatformFlavour",
        secondary=BuildPlatformFlavour,
    )
    products: Mapped[List["Product"]] = relationship(
        "Product",
        secondary="product_packages",
        back_populates="builds",
        cascade="all, delete",
        passive_deletes=True,
    )
    released: Mapped[bool] = mapped_column(sqlalchemy.Boolean, default=False)
    signed: Mapped[Optional[bool]] = mapped_column(
        sqlalchemy.Boolean, default=False, nullable=True
    )
    cancel_testing: Mapped[bool] = mapped_column(
        sqlalchemy.Boolean, default=False, nullable=False
    )


BuildTaskDependency = sqlalchemy.Table(
    "build_task_dependency",
    Base.metadata,
    sqlalchemy.Column(
        "build_task_id",
        sqlalchemy.Integer,
        sqlalchemy.ForeignKey("build_tasks.id"),
        primary_key=True,
    ),
    sqlalchemy.Column(
        "build_task_dependency",
        sqlalchemy.Integer,
        sqlalchemy.ForeignKey("build_tasks.id"),
        primary_key=True,
    ),
)


BuildTaskRpmModuleMapping = sqlalchemy.Table(
    "build_tasks_rpm_modules_mapping",
    Base.metadata,
    sqlalchemy.Column(
        "build_task_id",
        sqlalchemy.Integer,
        sqlalchemy.ForeignKey(
            "build_tasks.id",
            name="build_tasks_rpm_modules_mapping_build_task_id_fkey",
        ),
        primary_key=True,
    ),
    sqlalchemy.Column(
        "rpm_module_id",
        sqlalchemy.Integer,
        sqlalchemy.ForeignKey(
            "rpm_module.id",
            name="build_tasks_rpm_modules_mapping_rpm_module_id_fkey",
        ),
        primary_key=True,
    ),
)


class BuildTask(TimeMixin, Base):
    __tablename__ = "build_tasks"

    id: Mapped[int] = mapped_column(sqlalchemy.Integer, primary_key=True)
    ts: Mapped[Optional[datetime.datetime]] = mapped_column(
        sqlalchemy.DateTime,
        nullable=True,
        index=True,
    )
    build_id: Mapped[int] = mapped_column(
        sqlalchemy.Integer,
        sqlalchemy.ForeignKey("builds.id"),
        # saw https://stackoverflow.com/questions/
        # 5033547/sqlalchemy-cascade-delete
        nullable=False,
        index=True,
    )
    platform_id: Mapped[int] = mapped_column(
        sqlalchemy.Integer,
        sqlalchemy.ForeignKey("platforms.id"),
        nullable=False,
    )
    ref_id: Mapped[int] = mapped_column(
        sqlalchemy.Integer,
        sqlalchemy.ForeignKey("build_task_refs.id"),
        nullable=False,
        index=True,
    )
    rpm_modules: Mapped[List["RpmModule"]] = relationship(
        "RpmModule",
        secondary=BuildTaskRpmModuleMapping,
    )
    status: Mapped[int] = mapped_column(
        sqlalchemy.Integer,
        nullable=False,
        index=True,
    )
    index: Mapped[int] = mapped_column(sqlalchemy.Integer, nullable=False)
    arch: Mapped[str] = mapped_column(
        sqlalchemy.VARCHAR(length=50),
        nullable=False,
        index=True,
    )
    is_secure_boot: Mapped[Optional[bool]] = mapped_column(
        sqlalchemy.Boolean, default=False, nullable=True
    )
    mock_options: Mapped[Dict[str, Any]] = mapped_column(JSONB)
    ref: Mapped["BuildTaskRef"] = relationship("BuildTaskRef")
    alma_commit_cas_hash: Mapped[Optional[str]] = mapped_column(
        sqlalchemy.Text, nullable=True
    )
    is_cas_authenticated: Mapped[Optional[bool]] = mapped_column(
        sqlalchemy.Boolean, default=False, nullable=True
    )
    artifacts: Mapped[List["BuildTaskArtifact"]] = relationship(
        "BuildTaskArtifact", back_populates="build_task"
    )
    platform: Mapped["Platform"] = relationship("Platform")
    build: Mapped["Build"] = relationship("Build", back_populates="tasks")
    dependencies: Mapped[List["BuildTask"]] = relationship(
        "BuildTask",
        secondary=BuildTaskDependency,
        primaryjoin=(BuildTaskDependency.c.build_task_id == id),
        secondaryjoin=(BuildTaskDependency.c.build_task_dependency == id),
    )
    test_tasks: Mapped[List["TestTask"]] = relationship(
        "TestTask", back_populates="build_task", order_by="TestTask.revision"
    )
    performance_stats: Mapped[List["PerformanceStats"]] = relationship(
        "PerformanceStats",
        back_populates="build_task",
    )
    built_srpm_url: Mapped[Optional[str]] = mapped_column(
        sqlalchemy.VARCHAR, nullable=True
    )
    error: Mapped[Optional[str]] = mapped_column(
        sqlalchemy.Text, nullable=True, default=None
    )


class BuildTaskRef(Base):
    __tablename__ = "build_task_refs"

    id: Mapped[int] = mapped_column(sqlalchemy.Integer, primary_key=True)
    url: Mapped[str] = mapped_column(sqlalchemy.TEXT, nullable=False)
    git_ref: Mapped[Optional[str]] = mapped_column(sqlalchemy.TEXT)
    ref_type: Mapped[Optional[int]] = mapped_column(sqlalchemy.Integer)
    git_commit_hash: Mapped[Optional[str]] = mapped_column(
        sqlalchemy.TEXT, nullable=True
    )
    test_configuration: Mapped[Optional[Dict[str, Any]]] = mapped_column(
        JSONB, nullable=True
    )


class RpmModule(Base):
    __tablename__ = "rpm_module"

    id: Mapped[int] = mapped_column(sqlalchemy.Integer, primary_key=True)
    name: Mapped[str] = mapped_column(sqlalchemy.TEXT, nullable=False)
    version: Mapped[str] = mapped_column(sqlalchemy.TEXT, nullable=False)
    stream: Mapped[str] = mapped_column(sqlalchemy.TEXT, nullable=False)
    context: Mapped[str] = mapped_column(sqlalchemy.TEXT, nullable=False)
    arch: Mapped[str] = mapped_column(sqlalchemy.TEXT, nullable=False)
    pulp_href: Mapped[str] = mapped_column(sqlalchemy.TEXT, nullable=False)

    @property
    def nvsca(self):
        return (
            f"{self.name}-{self.version}-{self.stream}"
            f"-{self.context}-{self.arch}"
        )


class BuildTaskArtifact(Base):
    __tablename__ = "build_artifacts"

    id: Mapped[int] = mapped_column(sqlalchemy.Integer, primary_key=True)
    build_task_id: Mapped[int] = mapped_column(
        sqlalchemy.Integer,
        sqlalchemy.ForeignKey("build_tasks.id"),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(sqlalchemy.Text, nullable=False)
    type: Mapped[str] = mapped_column(sqlalchemy.Text, nullable=False)
    href: Mapped[str] = mapped_column(sqlalchemy.Text, nullable=False)
    build_task: Mapped["BuildTask"] = relationship(
        "BuildTask", back_populates="artifacts"
    )
    cas_hash: Mapped[Optional[str]] = mapped_column(
        sqlalchemy.Text, nullable=True
    )
    sign_key_id: Mapped[Optional[int]] = mapped_column(
        sqlalchemy.Integer,
        sqlalchemy.ForeignKey(
            "sign_keys.id",
            name="build_artifacts_sign_key_id_fkey",
        ),
        nullable=True,
    )
    sign_key: Mapped["SignKey"] = relationship(
        "SignKey", back_populates="build_task_artifacts"
    )

    def name_as_dict(self) -> dict:
        result = re.search(
            r"^(?P<name>[\w+-.]+)-"
            r"(?P<version>\d+?[\w.]*)-"
            r"(?P<release>\d+?[\w.+]*?)"
            r"\.(?P<arch>[\w]*)(\.rpm)?$",
            self.name,
        )
        if not result:
            return {}
        return result.groupdict()


class SourceRpm(Base):
    __tablename__ = "source_rpms"

    id: Mapped[int] = mapped_column(sqlalchemy.Integer, primary_key=True)
    build_id: Mapped[int] = mapped_column(
        sqlalchemy.Integer,
        sqlalchemy.ForeignKey("builds.id"),
        nullable=False,
        index=True,
    )
    build: Mapped["Build"] = relationship("Build", back_populates="source_rpms")
    artifact_id: Mapped[int] = mapped_column(
        sqlalchemy.Integer,
        sqlalchemy.ForeignKey("build_artifacts.id"),
        nullable=False,
    )
    artifact: Mapped["BuildTaskArtifact"] = relationship("BuildTaskArtifact")
    binary_rpms: Mapped[List["BinaryRpm"]] = relationship(
        "BinaryRpm", back_populates="source_rpm"
    )


class BinaryRpm(Base):
    __tablename__ = "binary_rpms"

    id: Mapped[int] = mapped_column(sqlalchemy.Integer, primary_key=True)
    build_id: Mapped[int] = mapped_column(
        sqlalchemy.Integer, sqlalchemy.ForeignKey("builds.id"), nullable=False
    )
    build: Mapped["Build"] = relationship("Build", back_populates="binary_rpms")
    artifact_id: Mapped[int] = mapped_column(
        sqlalchemy.Integer,
        sqlalchemy.ForeignKey("build_artifacts.id"),
        nullable=False,
    )
    artifact: Mapped["BuildTaskArtifact"] = relationship("BuildTaskArtifact")
    source_rpm_id: Mapped[int] = mapped_column(
        sqlalchemy.Integer,
        sqlalchemy.ForeignKey("source_rpms.id"),
        nullable=False,
    )
    source_rpm: Mapped["SourceRpm"] = relationship(
        "SourceRpm", back_populates="binary_rpms"
    )


class UserAction(Base):
    __tablename__ = "user_actions"

    id: Mapped[int] = mapped_column(sqlalchemy.Integer, primary_key=True)
    name: Mapped[str] = mapped_column(sqlalchemy.String(100), unique=True)
    description: Mapped[Optional[str]] = mapped_column(
        sqlalchemy.TEXT, nullable=True
    )


ActionRoleMapping = sqlalchemy.Table(
    "action_role_mapping",
    Base.metadata,
    sqlalchemy.Column(
        "action_id",
        sqlalchemy.Integer,
        sqlalchemy.ForeignKey(
            "user_actions.id",
            ondelete="CASCADE",
            name="fk_action_role_mapping_action_id",
        ),
        primary_key=True,
    ),
    sqlalchemy.Column(
        "role_id",
        sqlalchemy.Integer,
        sqlalchemy.ForeignKey(
            "user_roles.id",
            ondelete="CASCADE",
            name="fk_action_role_mapping_role_id",
        ),
        primary_key=True,
    ),
)


class UserRole(Base):
    __tablename__ = "user_roles"

    id: Mapped[int] = mapped_column(sqlalchemy.Integer, primary_key=True)
    name: Mapped[str] = mapped_column(sqlalchemy.String(100), unique=True)
    actions: Mapped[List["UserAction"]] = relationship(
        "UserAction", secondary=ActionRoleMapping
    )

    def __repr__(self):
        return f"{self.__class__.__name__}: {self.id} {self.name}"


UserRoleMapping = sqlalchemy.Table(
    "user_role_mapping",
    Base.metadata,
    sqlalchemy.Column(
        "user_id",
        sqlalchemy.Integer,
        sqlalchemy.ForeignKey(
            "users.id",
            ondelete="CASCADE",
            name="fk_user_role_mapping_user_id",
        ),
        primary_key=True,
    ),
    sqlalchemy.Column(
        "role_id",
        sqlalchemy.Integer,
        sqlalchemy.ForeignKey(
            "user_roles.id",
            ondelete="CASCADE",
            name="fk_user_role_mapping_role_id",
        ),
        primary_key=True,
    ),
)

ProductRoleMapping = sqlalchemy.Table(
    "product_role_mapping",
    Base.metadata,
    sqlalchemy.Column(
        "product_id",
        sqlalchemy.Integer,
        sqlalchemy.ForeignKey(
            "products.id",
            ondelete="CASCADE",
            name="fk_product_role_mapping_product_id",
        ),
        primary_key=True,
    ),
    sqlalchemy.Column(
        "role_id",
        sqlalchemy.Integer,
        sqlalchemy.ForeignKey(
            "user_roles.id",
            ondelete="CASCADE",
            name="fk_product_role_mapping_role_id",
        ),
        primary_key=True,
    ),
)

TeamRoleMapping = sqlalchemy.Table(
    "team_role_mapping",
    Base.metadata,
    sqlalchemy.Column(
        "team_id",
        sqlalchemy.Integer,
        sqlalchemy.ForeignKey(
            "teams.id",
            ondelete="CASCADE",
            name="fk_team_role_mapping_team_id",
        ),
        primary_key=True,
    ),
    sqlalchemy.Column(
        "role_id",
        sqlalchemy.Integer,
        sqlalchemy.ForeignKey(
            "user_roles.id",
            ondelete="CASCADE",
            name="fk_team_role_mapping_role_id",
        ),
        primary_key=True,
    ),
)


TestRepositoryRoleMapping = sqlalchemy.Table(
    "test_repository_role_mapping",
    Base.metadata,
    sqlalchemy.Column(
        "test_repository_id",
        sqlalchemy.Integer,
        sqlalchemy.ForeignKey(
            "test_repositories.id",
            ondelete="CASCADE",
            name="fk_test_repositories_role_mapping_product_id",
        ),
        primary_key=True,
    ),
    sqlalchemy.Column(
        "role_id",
        sqlalchemy.Integer,
        sqlalchemy.ForeignKey(
            "user_roles.id",
            ondelete="CASCADE",
            name="fk_test_repositories_role_mapping_role_id",
        ),
        primary_key=True,
    ),
)


TeamUserMapping = sqlalchemy.Table(
    "team_user_mapping",
    Base.metadata,
    sqlalchemy.Column(
        "team_id",
        sqlalchemy.Integer,
        sqlalchemy.ForeignKey("teams.id"),
        primary_key=True,
    ),
    sqlalchemy.Column(
        "user_id",
        sqlalchemy.Integer,
        sqlalchemy.ForeignKey("users.id"),
        primary_key=True,
    ),
)


class UserOauthAccount(SQLAlchemyBaseOAuthAccountTable[int], Base):
    __tablename__ = "user_oauth_accounts"

    id: Mapped[int] = mapped_column(sqlalchemy.Integer, primary_key=True)
    # Override SQLAlchemyBaseOAuthAccountTable access_token column length
    access_token: Mapped[str] = mapped_column(
        sqlalchemy.VARCHAR(length=2048),
        nullable=False,
    )

    @declared_attr
    def user_id(cls) -> Mapped[int]:
        return mapped_column(
            sqlalchemy.Integer,
            sqlalchemy.ForeignKey("users.id", ondelete="cascade"),
            nullable=False,
        )


class UserAccessToken(SQLAlchemyBaseAccessTokenTable[int], Base):
    __tablename__ = "user_access_tokens"

    id: Mapped[int] = mapped_column(
        sqlalchemy.Integer, primary_key=True, autoincrement=True
    )

    @declared_attr
    def user_id(cls) -> Mapped[int]:
        return mapped_column(
            sqlalchemy.Integer,
            sqlalchemy.ForeignKey("users.id", ondelete="cascade"),
            nullable=False,
        )


class User(SQLAlchemyBaseUserTable[int], Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(sqlalchemy.Integer, primary_key=True)
    username: Mapped[Optional[str]] = mapped_column(
        sqlalchemy.TEXT, nullable=True
    )
    first_name: Mapped[Optional[str]] = mapped_column(
        sqlalchemy.String(320), nullable=True
    )
    last_name: Mapped[Optional[str]] = mapped_column(
        sqlalchemy.String(320), nullable=True
    )
    # Override SQLAlchemyBaseUserTable email attribute to keep current type
    email: Mapped[str] = mapped_column(
        sqlalchemy.TEXT,
        unique=True,
        index=True,
        nullable=False,
    )
    hashed_password: Mapped[Optional[str]] = mapped_column(
        sqlalchemy.String(length=1024),
        nullable=True,
    )
    roles: Mapped[List["UserRole"]] = relationship(
        "UserRole", secondary=UserRoleMapping
    )
    teams: Mapped[List["Team"]] = relationship(
        "Team", secondary=TeamUserMapping, back_populates="members"
    )
    oauth_accounts: Mapped[List["UserOauthAccount"]] = relationship(
        "UserOauthAccount", lazy="joined"
    )


class Team(PermissionsMixin, Base):
    __tablename__ = "teams"

    id: Mapped[int] = mapped_column(sqlalchemy.Integer, primary_key=True)
    name: Mapped[str] = mapped_column(
        sqlalchemy.Text, nullable=False, unique=True
    )
    members: Mapped[List["User"]] = relationship(
        "User", secondary=TeamUserMapping, back_populates="teams"
    )
    products: Mapped[List["Product"]] = relationship(
        "Product", back_populates="team"
    )
    test_repositories: Mapped[List["TestRepository"]] = relationship(
         "TestRepository", back_populates="team"
    )
    roles: Mapped[List["UserRole"]] = relationship(
        "UserRole",
        secondary=TeamRoleMapping,
        cascade="all, delete",
    )


ProductRepositories = sqlalchemy.Table(
    "product_repositories",
    Base.metadata,
    sqlalchemy.Column(
        "product_id",
        sqlalchemy.Integer,
        sqlalchemy.ForeignKey(
            "products.id",
            name="fk_product_repositories_products_id",
        ),
        primary_key=True,
    ),
    sqlalchemy.Column(
        "repository_id",
        sqlalchemy.Integer,
        sqlalchemy.ForeignKey(
            "repositories.id",
            name="fk_product_repositories_repositories_id",
        ),
        primary_key=True,
    ),
)

ProductBuilds = sqlalchemy.Table(
    "product_packages",
    Base.metadata,
    sqlalchemy.Column(
        "product_id",
        sqlalchemy.Integer,
        sqlalchemy.ForeignKey(
            "products.id",
            name="fk_product_packages_products_id",
        ),
        primary_key=True,
    ),
    sqlalchemy.Column(
        "build_id",
        sqlalchemy.Integer,
        sqlalchemy.ForeignKey(
            "builds.id",
            name="fk_product_packages_builds_id",
        ),
        primary_key=True,
    ),
)

ProductPlatforms = sqlalchemy.Table(
    "product_platforms",
    Base.metadata,
    sqlalchemy.Column(
        "product_id",
        sqlalchemy.Integer,
        sqlalchemy.ForeignKey(
            "products.id",
            name="fk_product_platforms_products_id",
        ),
        primary_key=True,
    ),
    sqlalchemy.Column(
        "platform_id",
        sqlalchemy.Integer,
        sqlalchemy.ForeignKey(
            "platforms.id",
            name="fk_product_platforms_platforms_id",
        ),
        primary_key=True,
    ),
)


class Product(PermissionsMixin, TeamMixin, Base):
    __tablename__ = "products"

    id: Mapped[int] = mapped_column(sqlalchemy.Integer, primary_key=True)
    name: Mapped[str] = mapped_column(
        sqlalchemy.Text, nullable=False, unique=True
    )
    # FIXME: change nullable to False after population
    title: Mapped[Optional[str]] = mapped_column(
        sqlalchemy.String(100), nullable=True
    )
    description: Mapped[Optional[str]] = mapped_column(
        sqlalchemy.Text, nullable=True
    )
    team: Mapped["Team"] = relationship("Team", back_populates="products")
    is_community: Mapped[bool] = mapped_column(
        sqlalchemy.Boolean, nullable=False, default=True
    )
    roles: Mapped[List["UserRole"]] = relationship(
        "UserRole", secondary=ProductRoleMapping
    )
    repositories: Mapped[List["Repository"]] = relationship(
        "Repository",
        secondary=ProductRepositories,
        cascade="all, delete",
    )
    platforms: Mapped[List["Platform"]] = relationship(
        "Platform",
        secondary=ProductPlatforms,
    )
    builds: Mapped[List["Build"]] = relationship(
        "Build",
        secondary=ProductBuilds,
        back_populates="products",
    )
    sign_keys: Mapped[List["SignKey"]] = relationship(
        "SignKey",
        back_populates="product",
        cascade="all, delete-orphan",
    )

    @property
    def full_name(self) -> str:
        return f"{self.owner.username}/{self.name}"

    @property
    def pulp_base_distro_name(self) -> str:
        return f"{self.owner.username}-{self.name}"


class TestTask(TimeMixin, Base):
    __tablename__ = "test_tasks"

    id: Mapped[int] = mapped_column(sqlalchemy.Integer, primary_key=True)
    package_name: Mapped[str] = mapped_column(sqlalchemy.TEXT, nullable=False)
    package_version: Mapped[str] = mapped_column(
        sqlalchemy.TEXT, nullable=False
    )
    package_release: Mapped[Optional[str]] = mapped_column(
        sqlalchemy.TEXT, nullable=True
    )
    env_arch: Mapped[str] = mapped_column(sqlalchemy.TEXT, nullable=False)
    build_task_id: Mapped[int] = mapped_column(
        sqlalchemy.Integer,
        sqlalchemy.ForeignKey("build_tasks.id"),
        nullable=False,
        index=True,
    )
    build_task: Mapped["BuildTask"] = relationship(
        "BuildTask", back_populates="test_tasks"
    )
    status: Mapped[int] = mapped_column(
        sqlalchemy.Integer,
        nullable=False,
        index=True,
    )
    alts_response: Mapped[Optional[Dict[str, Any]]] = mapped_column(
        JSONB, nullable=True
    )
    revision: Mapped[int] = mapped_column(
        sqlalchemy.Integer,
        nullable=False,
        index=True,
    )
    artifacts: Mapped[List["TestTaskArtifact"]] = relationship(
        "TestTaskArtifact", back_populates="test_task"
    )
    repository_id: Mapped[int] = mapped_column(
        sqlalchemy.Integer,
        sqlalchemy.ForeignKey("repositories.id", name="test_task_repo_fk"),
        nullable=True,
    )
    repository: Mapped["Repository"] = relationship("Repository")
    scheduled_at: Mapped[Optional[datetime.datetime]] = mapped_column(
        sqlalchemy.DateTime, nullable=True
    )
    performance_stats: Mapped[List["PerformanceStats"]] = relationship(
        "PerformanceStats",
        back_populates="test_task",
    )


class TestTaskArtifact(Base):
    __tablename__ = "test_task_artifacts"
    id: Mapped[int] = mapped_column(sqlalchemy.Integer, primary_key=True)
    test_task_id: Mapped[int] = mapped_column(
        sqlalchemy.Integer,
        sqlalchemy.ForeignKey("test_tasks.id"),
        nullable=False,
    )
    test_task: Mapped["TestTask"] = relationship(
        "TestTask", back_populates="artifacts"
    )
    name: Mapped[str] = mapped_column(sqlalchemy.Text, nullable=False)
    href: Mapped[str] = mapped_column(sqlalchemy.Text, nullable=False)


class PackageTestRepository(Base):
    __tablename__ = "package_test_repository"
    __tableargs__ = [
        sqlalchemy.UniqueConstraint(
            "package_name",
            "folder_name",
            name="package_test_repo_uix",
        ),
    ]
    id: Mapped[int] = mapped_column(sqlalchemy.Integer, primary_key=True)
    package_name: Mapped[str] = mapped_column(sqlalchemy.Text, nullable=False)
    folder_name: Mapped[str] = mapped_column(sqlalchemy.Text, nullable=False)
    url: Mapped[str] = mapped_column(sqlalchemy.Text, nullable=False)
    test_repository_id: Mapped[int] = mapped_column(
        sqlalchemy.Integer,
        sqlalchemy.ForeignKey(
            "test_repositories.id",
            ondelete="CASCADE",
            name="fk_package_test_repository_id",
        ),
        nullable=False,
    )
    test_repository: Mapped["TestRepository"] = relationship(
        "TestRepository", back_populates="packages"
    )


class TestRepository(PermissionsMixin, TeamMixin, Base):
    __tablename__ = "test_repositories"
    id: Mapped[int] = mapped_column(sqlalchemy.Integer, primary_key=True)
    name: Mapped[str] = mapped_column(
        sqlalchemy.Text, nullable=False, unique=True
    )
    url: Mapped[str] = mapped_column(
        sqlalchemy.Text, nullable=False, unique=True
    )
    tests_dir: Mapped[str] = mapped_column(sqlalchemy.Text, nullable=False)
    tests_prefix: Mapped[Optional[str]] = mapped_column(
        sqlalchemy.Text, nullable=True
    )
    packages: Mapped[List["PackageTestRepository"]] = relationship(
        "PackageTestRepository",
        back_populates="test_repository",
        cascade="all, delete",
    )
    team: Mapped["Team"] = relationship("Team", back_populates="test_repositories")
    roles: Mapped[List["UserRole"]] = relationship(
        "UserRole", secondary=TestRepositoryRoleMapping
    )


class Release(PermissionsMixin, TeamMixin, TimeMixin, Base):
    __tablename__ = "build_releases"

    id: Mapped[int] = mapped_column(sqlalchemy.Integer, primary_key=True)
    build_ids: Mapped[List[int]] = mapped_column(
        sqlalchemy.ARRAY(sqlalchemy.Integer, dimensions=1), nullable=False
    )
    created_at: Mapped[Optional[datetime.datetime]] = mapped_column(
        sqlalchemy.DateTime,
        nullable=True,
        default=func.current_timestamp(),
    )
    build_task_ids: Mapped[List[int]] = mapped_column(
        sqlalchemy.ARRAY(sqlalchemy.Integer, dimensions=1), nullable=True
    )
    reference_platform_id: Mapped[Optional[int]] = mapped_column(
        sqlalchemy.Integer,
        nullable=True,
    )
    platform_id: Mapped[int] = mapped_column(
        sqlalchemy.Integer,
        sqlalchemy.ForeignKey("platforms.id"),
        nullable=False,
    )
    platform: Mapped["Platform"] = relationship("Platform")
    product_id: Mapped[int] = mapped_column(
        sqlalchemy.Integer,
        sqlalchemy.ForeignKey(
            "products.id",
            name="build_releases_product_id_fkey",
        ),
        nullable=False,
    )
    product: Mapped["Product"] = relationship("Product")
    plan: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSONB, nullable=True)
    status: Mapped[int] = mapped_column(
        sqlalchemy.Integer, default=ReleaseStatus.SCHEDULED
    )
    performance_stats: Mapped[List["PerformanceStats"]] = relationship(
        "PerformanceStats",
        back_populates="release",
    )


SignKeyRoleMapping = sqlalchemy.Table(
    "sign_key_role_mapping",
    Base.metadata,
    sqlalchemy.Column(
        "sign_key_id",
        sqlalchemy.Integer,
        sqlalchemy.ForeignKey(
            "sign_keys.id",
            ondelete="CASCADE",
            name="fk_sign_key_role_mapping_sign_key_id",
        ),
        primary_key=True,
    ),
    sqlalchemy.Column(
        "role_id",
        sqlalchemy.Integer,
        sqlalchemy.ForeignKey(
            "user_roles.id",
            ondelete="CASCADE",
            name="fk_sign_key_role_mapping_role_id",
        ),
        primary_key=True,
    ),
)


class SignKey(PermissionsMixin, Base):
    __tablename__ = "sign_keys"

    id: Mapped[int] = mapped_column(sqlalchemy.Integer, primary_key=True)
    name: Mapped[str] = mapped_column(sqlalchemy.Text)
    # FIXME: change nullable to False after population
    is_community: Mapped[Optional[bool]] = mapped_column(
        sqlalchemy.Boolean,
        nullable=True,
        default=False,
    )
    description: Mapped[Optional[str]] = mapped_column(
        sqlalchemy.Text, nullable=True
    )
    keyid: Mapped[str] = mapped_column(sqlalchemy.String(16), unique=True)
    fingerprint: Mapped[str] = mapped_column(sqlalchemy.String(40), unique=True)
    public_url: Mapped[str] = mapped_column(sqlalchemy.Text)
    inserted: Mapped[datetime.datetime] = mapped_column(
        sqlalchemy.DateTime, default=datetime.datetime.utcnow()
    )
    active: Mapped[bool] = mapped_column(
        sqlalchemy.Boolean, default=True
    )
    archived: Mapped[datetime.datetime] = mapped_column(
        sqlalchemy.DateTime, nullable=True,
    )
    product_id: Mapped[Optional[int]] = mapped_column(
        sqlalchemy.Integer,
        sqlalchemy.ForeignKey(
            'products.id',
            name='sign_keys_product_id_fkey',
        ),
        nullable=True,
    )
    product: Mapped["Product"] = relationship(
        'Product', back_populates='sign_keys'
    )
    platform_id: Mapped[Optional[int]] = mapped_column(
        sqlalchemy.Integer,
        sqlalchemy.ForeignKey(
            "platforms.id",
            name="sign_keys_platform_id_fkey",
        ),
        nullable=True,
    )
    platform: Mapped["Platform"] = relationship(
        "Platform", back_populates="sign_keys"
    )
    build_task_artifacts: Mapped[List["BuildTaskArtifact"]] = relationship(
        "BuildTaskArtifact",
        back_populates="sign_key",
    )
    roles: Mapped[List["UserRole"]] = relationship(
        "UserRole", secondary=SignKeyRoleMapping
    )


class GenKeyTask(Base):
    __tablename__ = "gen_key_tasks"

    id: Mapped[int] = mapped_column(sqlalchemy.Integer, primary_key=True)
    status: Mapped[int] = mapped_column(
        sqlalchemy.Integer, default=GenKeyStatus.IDLE
    )
    error_message: Mapped[Optional[str]] = mapped_column(
        sqlalchemy.Text, nullable=True
    )
    product: Mapped["Product"] = relationship("Product")
    product_id: Mapped[int] = mapped_column(
        sqlalchemy.Integer,
        sqlalchemy.ForeignKey("products.id"),
        nullable=False,
    )


class SignTask(TimeMixin, Base):
    __tablename__ = "sign_tasks"

    id: Mapped[int] = mapped_column(sqlalchemy.Integer, primary_key=True)
    build_id: Mapped[int] = mapped_column(
        sqlalchemy.Integer, sqlalchemy.ForeignKey("builds.id"), nullable=False
    )
    build: Mapped["Build"] = relationship("Build")
    sign_key_id: Mapped[int] = mapped_column(
        sqlalchemy.Integer,
        sqlalchemy.ForeignKey("sign_keys.id"),
        nullable=False,
    )
    sign_key: Mapped["SignKey"] = relationship("SignKey")
    status: Mapped[int] = mapped_column(
        sqlalchemy.Integer, default=SignStatus.IDLE
    )
    ts: Mapped[Optional[datetime.datetime]] = mapped_column(
        sqlalchemy.DateTime, nullable=True
    )
    error_message: Mapped[Optional[str]] = mapped_column(
        sqlalchemy.Text, nullable=True
    )
    log_href: Mapped[Optional[str]] = mapped_column(
        sqlalchemy.Text, nullable=True
    )
    stats: Mapped[Optional[Dict[str, Any]]] = mapped_column(
        JSONB, nullable=True
    )


class ExportTask(Base):
    __tablename__ = "export_tasks"

    id: Mapped[int] = mapped_column(sqlalchemy.Integer, primary_key=True)
    name: Mapped[str] = mapped_column(sqlalchemy.Text, nullable=False)
    status: Mapped[int] = mapped_column(sqlalchemy.Integer, nullable=False)
    exported_at: Mapped[Optional[datetime.datetime]] = mapped_column(
        sqlalchemy.DateTime, nullable=True
    )


class RepoExporter(Base):
    __tablename__ = "repo_exporters"

    id: Mapped[int] = mapped_column(sqlalchemy.Integer, primary_key=True)
    path: Mapped[str] = mapped_column(sqlalchemy.Text, nullable=False)
    exported_id: Mapped[int] = mapped_column(
        sqlalchemy.Integer,
        sqlalchemy.ForeignKey("export_tasks.id"),
        nullable=False,
    )
    repository_id: Mapped[int] = mapped_column(
        sqlalchemy.Integer,
        sqlalchemy.ForeignKey("repositories.id"),
        nullable=False,
    )
    repository: Mapped["Repository"] = relationship("Repository")
    fs_exporter_href: Mapped[str] = mapped_column(
        sqlalchemy.Text, nullable=False
    )


class PlatformFlavour(PermissionsMixin, Base):
    __tablename__ = "platform_flavours"

    id: Mapped[int] = mapped_column(sqlalchemy.Integer, primary_key=True)
    name: Mapped[str] = mapped_column(
        sqlalchemy.Text, nullable=False, unique=True
    )
    modularity: Mapped[Optional[Dict[str, Any]]] = mapped_column(
        JSONB, nullable=True
    )
    repos: Mapped[List["Repository"]] = relationship(
        "Repository", secondary=FlavourRepo
    )
    data: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSONB, nullable=True)


class NewErrataRecord(Base):
    __tablename__ = "new_errata_records"
    id: Mapped[str] = mapped_column(sqlalchemy.Text, primary_key=True)
    platform_id: Mapped[int] = mapped_column(
        sqlalchemy.Integer,
        sqlalchemy.ForeignKey(
            "platforms.id",
            name="new_errata_records_platform_id_fkey",
        ),
        nullable=False,
        primary_key=True,
    )
    platform: Mapped["Platform"] = relationship("Platform")
    module: Mapped[Optional[str]] = mapped_column(
        sqlalchemy.Text, nullable=True
    )
    release_status: Mapped[
        Optional[
            Literal[
                ErrataReleaseStatus.NOT_RELEASED,
                ErrataReleaseStatus.IN_PROGRESS,
                ErrataReleaseStatus.RELEASED,
                ErrataReleaseStatus.FAILED,
            ]
        ]
    ] = mapped_column(
        sqlalchemy.Enum(ErrataReleaseStatus, name='erratareleasestatus'),
        nullable=False,
    )
    last_release_log: Mapped[Optional[str]] = mapped_column(
        sqlalchemy.Text, nullable=True
    )
    summary: Mapped[Optional[str]] = mapped_column(
        sqlalchemy.Text, nullable=True
    )
    solution: Mapped[Optional[str]] = mapped_column(
        sqlalchemy.Text, nullable=True
    )

    freezed: Mapped[Optional[bool]] = mapped_column(
        sqlalchemy.Boolean, nullable=True
    )

    issued_date: Mapped[datetime.datetime] = mapped_column(
        sqlalchemy.DateTime, nullable=False
    )
    updated_date: Mapped[datetime.datetime] = mapped_column(
        sqlalchemy.DateTime, nullable=False
    )
    description: Mapped[Optional[str]] = mapped_column(
        sqlalchemy.Text, nullable=True
    )
    original_description: Mapped[str] = mapped_column(
        sqlalchemy.Text, nullable=False
    )
    title: Mapped[Optional[str]] = mapped_column(sqlalchemy.Text, nullable=True)
    oval_title: Mapped[Optional[str]] = mapped_column(
        sqlalchemy.Text, nullable=True
    )
    original_title: Mapped[str] = mapped_column(sqlalchemy.Text, nullable=False)
    contact_mail: Mapped[str] = mapped_column(sqlalchemy.Text, nullable=False)
    status: Mapped[str] = mapped_column(sqlalchemy.Text, nullable=False)
    version: Mapped[str] = mapped_column(sqlalchemy.Text, nullable=False)
    severity: Mapped[str] = mapped_column(sqlalchemy.Text, nullable=False)
    rights: Mapped[str] = mapped_column(sqlalchemy.Text, nullable=False)
    # OVAL-only fields
    definition_id: Mapped[str] = mapped_column(sqlalchemy.Text, nullable=False)
    definition_version: Mapped[str] = mapped_column(
        sqlalchemy.Text, nullable=False
    )
    definition_class: Mapped[str] = mapped_column(
        sqlalchemy.Text, nullable=False
    )
    affected_cpe: Mapped[List[Dict[str, Any]]] = mapped_column(
        JSONB, nullable=False, default=[]
    )
    criteria: Mapped[Optional[List[Dict[str, Any]]]] = mapped_column(
        JSONB, nullable=True
    )
    original_criteria: Mapped[Optional[List[Dict[str, Any]]]] = mapped_column(
        JSONB, nullable=True
    )
    tests: Mapped[Optional[List[Dict[str, Any]]]] = mapped_column(
        JSONB, nullable=True
    )
    original_tests: Mapped[Optional[List[Dict[str, Any]]]] = mapped_column(
        JSONB, nullable=True
    )
    objects: Mapped[Optional[List[Dict[str, Any]]]] = mapped_column(
        JSONB, nullable=True
    )
    original_objects: Mapped[Optional[List[Dict[str, Any]]]] = mapped_column(
        JSONB, nullable=True
    )
    states: Mapped[Optional[List[Dict[str, Any]]]] = mapped_column(
        JSONB, nullable=True
    )
    original_states: Mapped[Optional[List[Dict[str, Any]]]] = mapped_column(
        JSONB, nullable=True
    )
    variables: Mapped[Optional[List[Dict[str, Any]]]] = mapped_column(
        JSONB, nullable=True
    )
    original_variables: Mapped[Optional[List[Dict[str, Any]]]] = mapped_column(
        JSONB, nullable=True
    )

    references: Mapped[List["NewErrataReference"]] = relationship(
        "NewErrataReference",
        back_populates="platform_specific_errata_record",
    )
    packages: Mapped[List["NewErrataPackage"]] = relationship(
        "NewErrataPackage",
        back_populates="platform_specific_errata_record",
    )

    cves: Mapped[AssociationProxy[Any]] = association_proxy(
        "references", "cve_id"
    )

    def get_description(self):
        if self.description:
            return self.description
        return self.original_description

    def get_title(self):
        if self.title:
            return self.title
        return self.original_title

    def get_type(self):
        # Gets errata type from last part of errata id
        # For example, ALBS -> (BA) -> bugfix
        #              ALSA -> (SA) -> security
        #              ALEA -> (EA) -> enhancement
        return {
            "BA": "bugfix",
            "SA": "security",
            "EA": "enhancement",
        }[self.id[2:4]]


class NewErrataPackage(Base):
    __tablename__ = "new_errata_packages"
    __table_args__ = (
        sqlalchemy.ForeignKeyConstraint(
            ("errata_record_id", "platform_id"),
            [NewErrataRecord.id, NewErrataRecord.platform_id],
            name="new_errata_package_errata_record_platform_id_fkey",
        ),
    )

    id: Mapped[int] = mapped_column(sqlalchemy.Integer, primary_key=True)
    errata_record_id: Mapped[str] = mapped_column(sqlalchemy.Text)
    platform_id: Mapped[int] = mapped_column(sqlalchemy.Integer)
    platform_specific_errata_record: Mapped["NewErrataRecord"] = relationship(
        "NewErrataRecord",
        foreign_keys=[errata_record_id, platform_id],
        cascade="all, delete",
        primaryjoin="and_(NewErrataPackage.errata_record_id == NewErrataRecord.id,"
        "NewErrataPackage.platform_id == NewErrataRecord.platform_id)",
        back_populates="packages",
    )
    name: Mapped[str] = mapped_column(sqlalchemy.Text, nullable=False)
    version: Mapped[str] = mapped_column(sqlalchemy.Text, nullable=False)
    release: Mapped[str] = mapped_column(sqlalchemy.Text, nullable=False)
    epoch: Mapped[int] = mapped_column(sqlalchemy.Integer, nullable=False)
    arch: Mapped[str] = mapped_column(sqlalchemy.Text, nullable=False)
    source_srpm: Mapped[Optional[str]] = mapped_column(
        sqlalchemy.Text, nullable=True
    )
    reboot_suggested: Mapped[bool] = mapped_column(
        sqlalchemy.Boolean, nullable=False
    )
    albs_packages: Mapped[List["NewErrataToALBSPackage"]] = relationship(
        "NewErrataToALBSPackage",
        back_populates="errata_package",
        cascade="all, delete",
    )


class NewErrataReference(Base):
    __tablename__ = "new_errata_references"
    __table_args__ = (
        sqlalchemy.ForeignKeyConstraint(
            ("errata_record_id", "platform_id"),
            [NewErrataRecord.id, NewErrataRecord.platform_id],
            name="new_errata_references_errata_record_platform_id_fkey",
        ),
    )

    id: Mapped[int] = mapped_column(sqlalchemy.Integer, primary_key=True)
    href: Mapped[str] = mapped_column(sqlalchemy.Text, nullable=False)
    ref_id: Mapped[str] = mapped_column(sqlalchemy.Text, nullable=False)
    title: Mapped[str] = mapped_column(sqlalchemy.Text, nullable=False)
    ref_type: Mapped[
        Literal[
            ErrataReferenceType.cve,
            ErrataReferenceType.rhsa,
            ErrataReferenceType.self_ref,
            ErrataReferenceType.bugzilla,
        ]
    ] = mapped_column(sqlalchemy.Enum(ErrataReferenceType), nullable=False)
    errata_record_id: Mapped[str] = mapped_column(sqlalchemy.Text)
    platform_id: Mapped[int] = mapped_column(sqlalchemy.Integer)
    platform_specific_errata_record: Mapped["NewErrataRecord"] = relationship(
        "NewErrataRecord",
        foreign_keys=[errata_record_id, platform_id],
        cascade="all, delete",
        primaryjoin="and_(NewErrataReference.errata_record_id == NewErrataRecord.id,"
        "NewErrataReference.platform_id == NewErrataRecord.platform_id)",
        back_populates="references",
    )
    cve: Mapped["ErrataCVE"] = relationship("ErrataCVE", cascade="all, delete")
    cve_id: Mapped[Optional[str]] = mapped_column(
        sqlalchemy.Text,
        sqlalchemy.ForeignKey(
            "errata_cves.id",
            name="new_errata_reference_cve_id_fk",
            ondelete="CASCADE",
        ),
        nullable=True,
    )


class NewErrataToALBSPackage(Base):
    __tablename__ = "new_errata_to_albs_packages"
    __table_args___ = (
        sqlalchemy.CheckConstraint(
            "albs_artifact_id IS NOT NULL OR pulp_href IS NOT NULL",
            name="new_errata_to_albs_package_integrity_check",
        ),
    )

    id: Mapped[int] = mapped_column(sqlalchemy.Integer, primary_key=True)
    errata_package_id: Mapped[int] = mapped_column(
        sqlalchemy.Integer,
        sqlalchemy.ForeignKey(
            "new_errata_packages.id",
            name="new_errata_to_albs_package_errata_package_id_fk",
            ondelete="CASCADE",
        ),
        nullable=False,
        index=True,
    )
    errata_package: Mapped[Optional[int]] = relationship(
        "NewErrataPackage",
        back_populates="albs_packages",
    )
    albs_artifact_id = mapped_column(
        sqlalchemy.Integer,
        sqlalchemy.ForeignKey(
            "build_artifacts.id",
            name="new_errata_to_albs_packages_albs_artifact_id_fkey",
            ondelete="CASCADE",
        ),
        nullable=True,
    )
    build_artifact: Mapped["BuildTaskArtifact"] = relationship(
        "BuildTaskArtifact"
    )
    pulp_href: Mapped[Optional[str]] = mapped_column(
        sqlalchemy.Text, nullable=True
    )
    status: Mapped[
        Literal[
            ErrataPackageStatus.proposal,
            ErrataPackageStatus.skipped,
            ErrataPackageStatus.released,
            ErrataPackageStatus.approved,
        ]
    ] = mapped_column(
        sqlalchemy.Enum(ErrataPackageStatus),
        nullable=False,
    )

    name: Mapped[str] = mapped_column(sqlalchemy.Text, nullable=False)
    arch: Mapped[str] = mapped_column(sqlalchemy.Text, nullable=False)
    version: Mapped[str] = mapped_column(sqlalchemy.Text, nullable=False)
    release: Mapped[str] = mapped_column(sqlalchemy.Text, nullable=False)
    epoch: Mapped[int] = mapped_column(sqlalchemy.Integer, nullable=False)

    @property
    def build_id(self):
        if self.build_artifact:
            return self.build_artifact.build_task.build_id

    @property
    def task_id(self):
        if self.build_artifact:
            return self.build_artifact.build_task.id

    def get_pulp_href(self):
        if self.pulp_href:
            return self.pulp_href
        return self.build_artifact.href


# Errata/OVAL related tables
class ErrataRecord(Base):
    __tablename__ = "errata_records"

    id: Mapped[str] = mapped_column(sqlalchemy.Text, primary_key=True)
    platform_id: Mapped[int] = mapped_column(
        sqlalchemy.Integer,
        sqlalchemy.ForeignKey("platforms.id"),
        nullable=False,
    )
    platform: Mapped["Platform"] = relationship("Platform")
    module: Mapped[Optional[str]] = mapped_column(
        sqlalchemy.Text, nullable=True
    )
    release_status: Mapped[
        Optional[
            Literal[
                ErrataReleaseStatus.NOT_RELEASED,
                ErrataReleaseStatus.IN_PROGRESS,
                ErrataReleaseStatus.RELEASED,
                ErrataReleaseStatus.FAILED,
            ]
        ]
    ] = mapped_column(
        sqlalchemy.Enum(ErrataReleaseStatus),
        nullable=True,
    )
    last_release_log: Mapped[Optional[str]] = mapped_column(
        sqlalchemy.Text, nullable=True
    )
    summary: Mapped[Optional[str]] = mapped_column(
        sqlalchemy.Text, nullable=True
    )
    solution: Mapped[Optional[str]] = mapped_column(
        sqlalchemy.Text, nullable=True
    )

    freezed: Mapped[Optional[bool]] = mapped_column(
        sqlalchemy.Boolean, nullable=True
    )

    issued_date: Mapped[datetime.datetime] = mapped_column(
        sqlalchemy.DateTime, nullable=False
    )
    updated_date: Mapped[datetime.datetime] = mapped_column(
        sqlalchemy.DateTime, nullable=False
    )
    description: Mapped[Optional[str]] = mapped_column(
        sqlalchemy.Text, nullable=True
    )
    original_description: Mapped[str] = mapped_column(
        sqlalchemy.Text, nullable=False
    )
    title: Mapped[Optional[str]] = mapped_column(sqlalchemy.Text, nullable=True)
    oval_title: Mapped[Optional[str]] = mapped_column(
        sqlalchemy.Text, nullable=True
    )
    original_title: Mapped[str] = mapped_column(sqlalchemy.Text, nullable=False)
    contact_mail: Mapped[str] = mapped_column(sqlalchemy.Text, nullable=False)
    status: Mapped[str] = mapped_column(sqlalchemy.Text, nullable=False)
    version: Mapped[str] = mapped_column(sqlalchemy.Text, nullable=False)
    severity: Mapped[str] = mapped_column(sqlalchemy.Text, nullable=False)
    rights: Mapped[str] = mapped_column(sqlalchemy.Text, nullable=False)
    # OVAL-only fields
    definition_id: Mapped[str] = mapped_column(sqlalchemy.Text, nullable=False)
    definition_version: Mapped[str] = mapped_column(
        sqlalchemy.Text, nullable=False
    )
    definition_class: Mapped[str] = mapped_column(
        sqlalchemy.Text, nullable=False
    )
    affected_cpe: Mapped[List[Dict[str, Any]]] = mapped_column(
        JSONB, nullable=False, default=[]
    )
    criteria: Mapped[Optional[List[Dict[str, Any]]]] = mapped_column(
        JSONB, nullable=True
    )
    original_criteria: Mapped[Optional[List[Dict[str, Any]]]] = mapped_column(
        JSONB, nullable=True
    )
    tests: Mapped[Optional[List[Dict[str, Any]]]] = mapped_column(
        JSONB, nullable=True
    )
    original_tests: Mapped[Optional[List[Dict[str, Any]]]] = mapped_column(
        JSONB, nullable=True
    )
    objects: Mapped[Optional[List[Dict[str, Any]]]] = mapped_column(
        JSONB, nullable=True
    )
    original_objects: Mapped[Optional[List[Dict[str, Any]]]] = mapped_column(
        JSONB, nullable=True
    )
    states: Mapped[Optional[List[Dict[str, Any]]]] = mapped_column(
        JSONB, nullable=True
    )
    original_states: Mapped[Optional[List[Dict[str, Any]]]] = mapped_column(
        JSONB, nullable=True
    )
    variables: Mapped[Optional[List[Dict[str, Any]]]] = mapped_column(
        JSONB, nullable=True
    )
    original_variables: Mapped[Optional[List[Dict[str, Any]]]] = mapped_column(
        JSONB, nullable=True
    )

    references: Mapped[List["ErrataReference"]] = relationship(
        "ErrataReference", cascade="all, delete"
    )
    packages: Mapped[List["ErrataPackage"]] = relationship(
        "ErrataPackage", cascade="all, delete"
    )

    cves: Mapped[AssociationProxy[Any]] = association_proxy(
        "references", "cve_id"
    )

    def get_description(self):
        if self.description:
            return self.description
        return self.original_description

    def get_title(self):
        if self.title:
            return self.title
        return self.original_title

    def get_type(self):
        # Gets errata type from last part of errata id
        # For example, ALBS -> (BA) -> bugfix
        #              ALSA -> (SA) -> security
        #              ALEA -> (EA) -> enhancement
        return {
            "BA": "bugfix",
            "SA": "security",
            "EA": "enhancement",
        }[self.id[2:4]]


class ErrataReference(Base):
    __tablename__ = "errata_references"

    id: Mapped[int] = mapped_column(sqlalchemy.Integer, primary_key=True)
    href: Mapped[str] = mapped_column(sqlalchemy.Text, nullable=False)
    ref_id: Mapped[str] = mapped_column(sqlalchemy.Text, nullable=False)
    title: Mapped[str] = mapped_column(sqlalchemy.Text, nullable=False)
    ref_type: Mapped[
        Literal[
            ErrataReferenceType.cve,
            ErrataReferenceType.rhsa,
            ErrataReferenceType.self_ref,
            ErrataReferenceType.bugzilla,
        ]
    ] = mapped_column(sqlalchemy.Enum(ErrataReferenceType), nullable=False)
    errata_record_id: Mapped[str] = mapped_column(
        sqlalchemy.Text,
        sqlalchemy.ForeignKey(
            "errata_records.id",
            name="errata_reference_errata_record_id_fk",
            ondelete="CASCADE",
        ),
        nullable=False,
        index=True,
    )
    cve: Mapped["ErrataCVE"] = relationship("ErrataCVE", cascade="all, delete")
    cve_id: Mapped[Optional[str]] = mapped_column(
        sqlalchemy.Text,
        sqlalchemy.ForeignKey(
            "errata_cves.id",
            name="errata_reference_cve_id_fk",
            ondelete="CASCADE",
        ),
        nullable=True,
    )


class ErrataCVE(Base):
    __tablename__ = "errata_cves"

    id: Mapped[str] = mapped_column(sqlalchemy.Text, primary_key=True)
    cvss3: Mapped[str] = mapped_column(sqlalchemy.Text, nullable=False)
    cwe: Mapped[Optional[str]] = mapped_column(sqlalchemy.Text, nullable=True)
    impact: Mapped[Optional[str]] = mapped_column(
        sqlalchemy.Text, nullable=True
    )
    public: Mapped[str] = mapped_column(sqlalchemy.Text, nullable=False)


class ErrataPackage(Base):
    __tablename__ = "errata_packages"

    id: Mapped[int] = mapped_column(sqlalchemy.Integer, primary_key=True)
    errata_record_id: Mapped[str] = mapped_column(
        sqlalchemy.Text,
        sqlalchemy.ForeignKey(
            "errata_records.id",
            name="errata_package_errata_record_id_fk",
            ondelete="CASCADE",
        ),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(sqlalchemy.Text, nullable=False)
    version: Mapped[str] = mapped_column(sqlalchemy.Text, nullable=False)
    release: Mapped[str] = mapped_column(sqlalchemy.Text, nullable=False)
    epoch: Mapped[int] = mapped_column(sqlalchemy.Integer, nullable=False)
    arch: Mapped[str] = mapped_column(sqlalchemy.Text, nullable=False)
    source_srpm: Mapped[Optional[str]] = mapped_column(
        sqlalchemy.Text, nullable=True
    )
    reboot_suggested: Mapped[bool] = mapped_column(
        sqlalchemy.Boolean, nullable=False
    )
    albs_packages: Mapped[List["ErrataToALBSPackage"]] = relationship(
        "ErrataToALBSPackage",
        back_populates="errata_package",
        cascade="all, delete",
    )


class ErrataToALBSPackage(Base):
    __tablename__ = "errata_to_albs_packages"
    __table_args___ = (
        sqlalchemy.CheckConstraint(
            "albs_artifact_id IS NOT NULL OR pulp_href IS NOT NULL",
            name="errata_to_albs_package_integrity_check",
        ),
    )

    id: Mapped[int] = mapped_column(sqlalchemy.Integer, primary_key=True)
    errata_package_id: Mapped[int] = mapped_column(
        sqlalchemy.Integer,
        sqlalchemy.ForeignKey(
            "errata_packages.id",
            name="errata_to_albs_package_errata_package_id_fk",
            ondelete="CASCADE",
        ),
        nullable=False,
        index=True,
    )
    errata_package: Mapped["ErrataPackage"] = relationship(
        "ErrataPackage",
        back_populates="albs_packages",
    )
    albs_artifact_id: Mapped[Optional[int]] = mapped_column(
        sqlalchemy.Integer,
        sqlalchemy.ForeignKey(
            "build_artifacts.id",
            name="errata_to_albs_packages_albs_artifact_id_fkey",
            ondelete="CASCADE",
        ),
        nullable=True,
    )
    build_artifact: Mapped["BuildTaskArtifact"] = relationship(
        "BuildTaskArtifact"
    )
    pulp_href: Mapped[Optional[str]] = mapped_column(
        sqlalchemy.Text, nullable=True
    )
    status: Mapped[
        Literal[
            ErrataPackageStatus.proposal,
            ErrataPackageStatus.skipped,
            ErrataPackageStatus.released,
            ErrataPackageStatus.approved,
        ]
    ] = mapped_column(
        sqlalchemy.Enum(ErrataPackageStatus),
        nullable=False,
    )

    name: Mapped[str] = mapped_column(sqlalchemy.Text, nullable=False)
    arch: Mapped[str] = mapped_column(sqlalchemy.Text, nullable=False)
    version: Mapped[str] = mapped_column(sqlalchemy.Text, nullable=False)
    release: Mapped[str] = mapped_column(sqlalchemy.Text, nullable=False)
    epoch: Mapped[int] = mapped_column(sqlalchemy.Integer, nullable=False)

    @property
    def build_id(self):
        if self.build_artifact:
            return self.build_artifact.build_task.build_id

    @property
    def task_id(self):
        if self.build_artifact:
            return self.build_artifact.build_task.id

    def get_pulp_href(self):
        if self.pulp_href:
            return self.pulp_href
        return self.build_artifact.href


class PerformanceStats(Base):
    __tablename__ = "performance_stats"

    id: Mapped[int] = mapped_column(sqlalchemy.Integer, primary_key=True)
    statistics: Mapped[Optional[Dict[str, Any]]] = mapped_column(
        JSONB,
        nullable=True,
    )
    build_task_id: Mapped[Optional[int]] = mapped_column(
        sqlalchemy.Integer,
        sqlalchemy.ForeignKey(
            "build_tasks.id",
            name="perf_stats_build_task_id",
        ),
        nullable=True,
        index=True,
    )
    build_task: Mapped["BuildTask"] = relationship(
        "BuildTask",
        back_populates="performance_stats",
    )
    test_task_id: Mapped[Optional[int]] = mapped_column(
        sqlalchemy.Integer,
        sqlalchemy.ForeignKey("test_tasks.id", name="perf_stats_test_task_id"),
        nullable=True,
        index=True,
    )
    test_task: Mapped["TestTask"] = relationship(
        "TestTask",
        back_populates="performance_stats",
    )
    release_id: Mapped[Optional[int]] = mapped_column(
        sqlalchemy.Integer,
        sqlalchemy.ForeignKey(
            "build_releases.id",
            name="perf_stats_build_release_id",
        ),
        nullable=True,
        index=True,
    )
    release: Mapped["Release"] = relationship(
        "Release",
        back_populates="performance_stats",
    )


idx_build_tasks_status_arch_ts = sqlalchemy.Index(
    "idx_build_tasks_status_arch_ts",
    BuildTask.status,
    BuildTask.arch,
    BuildTask.ts,
)
idx_build_tasks_build_id_index = sqlalchemy.Index(
    "idx_build_tasks_build_id_index",
    BuildTask.build_id,
    BuildTask.index,
)
idx_build_tasks_build_id_index_status = sqlalchemy.Index(
    "idx_build_tasks_build_id_index_status",
    BuildTask.build_id,
    BuildTask.index,
    BuildTask.status,
)
idx_build_tasks_build_id_status = sqlalchemy.Index(
    "idx_build_tasks_build_id_status",
    BuildTask.build_id,
    BuildTask.status,
)
idx_test_tasks_build_task_id_revision = sqlalchemy.Index(
    "idx_test_tasks_build_task_id_revision",
    TestTask.build_task_id,
    TestTask.revision,
)
idx_build_artifacts_build_task_id_type = sqlalchemy.Index(
    "idx_build_artifacts_build_task_id_type",
    BuildTaskArtifact.build_task_id,
    BuildTaskArtifact.type,
)
idx_build_artifacts_build_task_id_name_type = sqlalchemy.Index(
    "idx_build_artifacts_build_task_id_name_type",
    BuildTaskArtifact.build_task_id,
    BuildTaskArtifact.name,
    BuildTaskArtifact.type,
)
idx_errata_packages_name_version = sqlalchemy.Index(
    "idx_errata_packages_name_version",
    ErrataPackage.name,
    ErrataPackage.version,
)
idx_errata_packages_name_version_arch = sqlalchemy.Index(
    "idx_errata_packages_name_version_arch",
    ErrataPackage.name,
    ErrataPackage.version,
    ErrataPackage.arch,
)
idx_new_errata_packages_name_version = sqlalchemy.Index(
    "idx_new_errata_packages_name_version",
    ErrataPackage.name,
    ErrataPackage.version,
)
idx_new_errata_packages_name_version_arch = sqlalchemy.Index(
    "idx_new_errata_packages_name_version_arch",
    ErrataPackage.name,
    ErrataPackage.version,
    ErrataPackage.arch,
)
new_errata_records_id_platform_id_index = sqlalchemy.Index(
    "new_errata_records_id_platform_id_index",
    NewErrataRecord.id,
    NewErrataRecord.platform_id,
)
new_errata_packages_errata_record_id_platform_id_index = sqlalchemy.Index(
    "new_errata_packages_errata_record_id_platform_id_index",
    NewErrataPackage.errata_record_id,
    NewErrataPackage.platform_id,
)
new_errata_references_errata_record_id_platform_id_index = sqlalchemy.Index(
    "new_errata_references_errata_record_id_platform_id_index",
    NewErrataReference.errata_record_id,
    NewErrataReference.platform_id,
)


async def create_tables():
    engine = create_async_engine(settings.database_url, echo_pool=True)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


if __name__ == "__main__":
    asyncio.run(create_tables())

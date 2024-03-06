import asyncio
import datetime
import re
from typing import Dict, List

import sqlalchemy
from fastapi_users.db import (
    SQLAlchemyBaseOAuthAccountTable,
    SQLAlchemyBaseUserTable,
)
from fastapi_users_db_sqlalchemy.access_token import (
    SQLAlchemyBaseAccessTokenTable,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.associationproxy import association_proxy
from sqlalchemy.orm import (
    declarative_mixin,
    declared_attr,
    mapped_column,
    relationship,
)
from sqlalchemy.sql import func

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
from alws.database import Base, engine

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
    def team_id(cls):
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
    def team(cls):
        return relationship("Team")


@declarative_mixin
class PermissionsMixin:
    @declared_attr
    def owner_id(cls):
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
    def owner(cls):
        return relationship("User")

    permissions = mapped_column(
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
    def started_at(cls):
        return mapped_column(sqlalchemy.DateTime, nullable=True)

    @declared_attr
    def finished_at(cls):
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

    id = mapped_column(sqlalchemy.Integer, primary_key=True)
    contact_mail = mapped_column(sqlalchemy.Text, nullable=True)
    copyright = mapped_column(sqlalchemy.Text, nullable=True)
    type = mapped_column(sqlalchemy.Text, nullable=False)
    distr_type = mapped_column(sqlalchemy.Text, nullable=False)
    distr_version = mapped_column(sqlalchemy.Text, nullable=False)
    module_build_index = mapped_column(sqlalchemy.Integer, default=1)
    modularity = mapped_column(JSONB, nullable=True)
    test_dist_name = mapped_column(sqlalchemy.Text, nullable=False)
    name = mapped_column(
        sqlalchemy.Text, nullable=False, unique=True, index=True
    )
    priority = mapped_column(sqlalchemy.Integer, nullable=True)
    arch_list = mapped_column(JSONB, nullable=False)
    copy_priority_arches = mapped_column(JSONB, nullable=True)
    weak_arch_list = mapped_column(JSONB, nullable=True)
    data = mapped_column(JSONB, nullable=False)
    is_reference = mapped_column(
        sqlalchemy.Boolean, default=False, nullable=True
    )
    reference_platforms = relationship(
        "Platform",
        secondary=ReferencePlatforms,
        primaryjoin=(ReferencePlatforms.c.platform_id == id),
        secondaryjoin=(ReferencePlatforms.c.refefence_platform_id == id),
    )
    repos = relationship("Repository", secondary=PlatformRepo)
    sign_keys = relationship("SignKey", back_populates="platform")
    roles = relationship("UserRole", secondary=PlatformRoleMapping)


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

    id = mapped_column(sqlalchemy.Integer, primary_key=True)
    name = mapped_column(sqlalchemy.Text, nullable=False)
    arch = mapped_column(sqlalchemy.Text, nullable=False)
    url = mapped_column(sqlalchemy.Text, nullable=False)
    type = mapped_column(sqlalchemy.Text, nullable=False)
    debug = mapped_column(sqlalchemy.Boolean, default=False)
    mock_enabled = mapped_column(
        sqlalchemy.Boolean,
        default=True,
        nullable=True,
    )
    production = mapped_column(
        sqlalchemy.Boolean, default=False, nullable=True
    )
    pulp_href = mapped_column(sqlalchemy.Text)
    export_path = mapped_column(sqlalchemy.Text, nullable=True)
    priority = mapped_column(sqlalchemy.Integer, default=10, nullable=False)
    platform_id = mapped_column(
        sqlalchemy.Integer,
        sqlalchemy.ForeignKey("platforms.id"),
        nullable=True,
    )
    platform = relationship("Platform")


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

    id = mapped_column(sqlalchemy.Integer, primary_key=True)
    name = mapped_column(sqlalchemy.Text, nullable=False)
    arch = mapped_column(sqlalchemy.Text, nullable=False)
    url = mapped_column(sqlalchemy.Text, nullable=False)
    pulp_href = mapped_column(sqlalchemy.Text, nullable=False)


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

    id = mapped_column(sqlalchemy.Integer, primary_key=True)
    created_at = mapped_column(
        sqlalchemy.DateTime,
        nullable=False,
        default=func.current_timestamp(),
    )
    finished_at = mapped_column(sqlalchemy.DateTime, nullable=True)
    tasks = relationship("BuildTask", back_populates="build")
    sign_tasks = relationship(
        "SignTask",
        back_populates="build",
        order_by="SignTask.id",
    )
    repos = relationship("Repository", secondary=BuildRepo)
    linked_builds = relationship(
        "Build",
        secondary=BuildDependency,
        primaryjoin=(BuildDependency.c.build_id == id),
        secondaryjoin=(BuildDependency.c.build_dependency == id),
    )
    mock_options = mapped_column(JSONB)
    release_id = mapped_column(
        sqlalchemy.Integer,
        sqlalchemy.ForeignKey(
            "build_releases.id",
            name="build_releases_id_fkey",
        ),
        nullable=True,
    )
    release = relationship("Release")
    source_rpms = relationship("SourceRpm", back_populates="build")
    binary_rpms = relationship("BinaryRpm", back_populates="build")
    platform_flavors = relationship(
        "PlatformFlavour",
        secondary=BuildPlatformFlavour,
    )
    products = relationship(
        "Product",
        secondary="product_packages",
        back_populates="builds",
        cascade="all, delete",
        passive_deletes=True,
    )
    released = mapped_column(sqlalchemy.Boolean, default=False)
    signed = mapped_column(sqlalchemy.Boolean, default=False, nullable=True)
    cancel_testing = mapped_column(
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


class BuildTask(TimeMixin, Base):
    __tablename__ = "build_tasks"

    id = mapped_column(sqlalchemy.Integer, primary_key=True)
    ts = mapped_column(
        sqlalchemy.DateTime,
        nullable=True,
        index=True,
    )
    build_id = mapped_column(
        sqlalchemy.Integer,
        sqlalchemy.ForeignKey("builds.id"),
        # saw https://stackoverflow.com/questions/
        # 5033547/sqlalchemy-cascade-delete
        nullable=False,
        index=True,
    )
    platform_id = mapped_column(
        sqlalchemy.Integer,
        sqlalchemy.ForeignKey("platforms.id"),
        nullable=False,
    )
    ref_id = mapped_column(
        sqlalchemy.Integer,
        sqlalchemy.ForeignKey("build_task_refs.id"),
        nullable=False,
        index=True,
    )
    rpm_module_id = mapped_column(
        sqlalchemy.Integer,
        sqlalchemy.ForeignKey("rpm_module.id"),
        nullable=True,
    )
    status = mapped_column(
        sqlalchemy.Integer,
        nullable=False,
        index=True,
    )
    index = mapped_column(sqlalchemy.Integer, nullable=False)
    arch = mapped_column(
        sqlalchemy.VARCHAR(length=50),
        nullable=False,
        index=True,
    )
    is_secure_boot = mapped_column(
        sqlalchemy.Boolean, default=False, nullable=True
    )
    mock_options = mapped_column(JSONB)
    ref = relationship("BuildTaskRef")
    alma_commit_cas_hash = mapped_column(sqlalchemy.Text, nullable=True)
    is_cas_authenticated = mapped_column(
        sqlalchemy.Boolean, default=False, nullable=True
    )
    artifacts = relationship("BuildTaskArtifact", back_populates="build_task")
    platform = relationship("Platform")
    build = relationship("Build", back_populates="tasks")
    dependencies = relationship(
        "BuildTask",
        secondary=BuildTaskDependency,
        primaryjoin=(BuildTaskDependency.c.build_task_id == id),
        secondaryjoin=(BuildTaskDependency.c.build_task_dependency == id),
    )
    test_tasks = relationship(
        "TestTask", back_populates="build_task", order_by="TestTask.revision"
    )
    rpm_module = relationship("RpmModule")
    performance_stats: "PerformanceStats" = relationship(
        "PerformanceStats",
        back_populates="build_task",
    )
    built_srpm_url = mapped_column(sqlalchemy.VARCHAR, nullable=True)
    error = mapped_column(sqlalchemy.Text, nullable=True, default=None)


class BuildTaskRef(Base):
    __tablename__ = "build_task_refs"

    id = mapped_column(sqlalchemy.Integer, primary_key=True)
    url = mapped_column(sqlalchemy.TEXT, nullable=False)
    git_ref = mapped_column(sqlalchemy.TEXT)
    ref_type = mapped_column(sqlalchemy.Integer)
    git_commit_hash = mapped_column(sqlalchemy.TEXT, nullable=True)
    test_configuration = mapped_column(JSONB, nullable=True)


class RpmModule(Base):
    __tablename__ = "rpm_module"

    id = mapped_column(sqlalchemy.Integer, primary_key=True)
    name = mapped_column(sqlalchemy.TEXT, nullable=False)
    version = mapped_column(sqlalchemy.TEXT, nullable=False)
    stream = mapped_column(sqlalchemy.TEXT, nullable=False)
    context = mapped_column(sqlalchemy.TEXT, nullable=False)
    arch = mapped_column(sqlalchemy.TEXT, nullable=False)
    pulp_href = mapped_column(sqlalchemy.TEXT, nullable=False)
    sha256 = mapped_column(sqlalchemy.VARCHAR(64), nullable=True)

    @property
    def nvsca(self):
        return (
            f"{self.name}-{self.version}-{self.stream}"
            f"-{self.context}-{self.arch}"
        )


class BuildTaskArtifact(Base):
    __tablename__ = "build_artifacts"

    id = mapped_column(sqlalchemy.Integer, primary_key=True)
    build_task_id = mapped_column(
        sqlalchemy.Integer,
        sqlalchemy.ForeignKey("build_tasks.id"),
        nullable=False,
        index=True,
    )
    name = mapped_column(sqlalchemy.Text, nullable=False)
    type = mapped_column(sqlalchemy.Text, nullable=False)
    href = mapped_column(sqlalchemy.Text, nullable=False)
    build_task = relationship("BuildTask", back_populates="artifacts")
    cas_hash = mapped_column(sqlalchemy.Text, nullable=True)
    sign_key_id = mapped_column(
        sqlalchemy.Integer,
        sqlalchemy.ForeignKey(
            "sign_keys.id",
            name="build_artifacts_sign_key_id_fkey",
        ),
        nullable=True,
    )
    sign_key = relationship("SignKey", back_populates="build_task_artifacts")

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

    id = mapped_column(sqlalchemy.Integer, primary_key=True)
    build_id = mapped_column(
        sqlalchemy.Integer,
        sqlalchemy.ForeignKey("builds.id"),
        nullable=False,
        index=True,
    )
    build = relationship("Build", back_populates="source_rpms")
    artifact_id = mapped_column(
        sqlalchemy.Integer,
        sqlalchemy.ForeignKey("build_artifacts.id"),
        nullable=False,
    )
    artifact = relationship("BuildTaskArtifact")
    binary_rpms = relationship("BinaryRpm", back_populates="source_rpm")


class BinaryRpm(Base):
    __tablename__ = "binary_rpms"

    id = mapped_column(sqlalchemy.Integer, primary_key=True)
    build_id = mapped_column(
        sqlalchemy.Integer, sqlalchemy.ForeignKey("builds.id"), nullable=False
    )
    build = relationship("Build", back_populates="binary_rpms")
    artifact_id = mapped_column(
        sqlalchemy.Integer,
        sqlalchemy.ForeignKey("build_artifacts.id"),
        nullable=False,
    )
    artifact = relationship("BuildTaskArtifact")
    source_rpm_id = mapped_column(
        sqlalchemy.Integer,
        sqlalchemy.ForeignKey("source_rpms.id"),
        nullable=False,
    )
    source_rpm = relationship("SourceRpm", back_populates="binary_rpms")


class UserAction(Base):
    __tablename__ = "user_actions"

    id = mapped_column(sqlalchemy.Integer, primary_key=True)
    name = mapped_column(sqlalchemy.String(100), unique=True)
    description = mapped_column(sqlalchemy.TEXT, nullable=True)


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

    id = mapped_column(sqlalchemy.Integer, primary_key=True)
    name = mapped_column(sqlalchemy.String(100), unique=True)
    actions = relationship("UserAction", secondary=ActionRoleMapping)

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

    id = mapped_column(sqlalchemy.Integer, primary_key=True)
    # Override SQLAlchemyBaseOAuthAccountTable access_token column length
    access_token = mapped_column(
        sqlalchemy.VARCHAR(length=2048),
        nullable=False,
    )

    @declared_attr
    def user_id(cls):
        return mapped_column(
            sqlalchemy.Integer,
            sqlalchemy.ForeignKey("users.id", ondelete="cascade"),
            nullable=False,
        )


class UserAccessToken(SQLAlchemyBaseAccessTokenTable[int], Base):
    __tablename__ = "user_access_tokens"

    id = mapped_column(
        sqlalchemy.Integer, primary_key=True, autoincrement=True
    )

    @declared_attr
    def user_id(cls):
        return mapped_column(
            sqlalchemy.Integer,
            sqlalchemy.ForeignKey("users.id", ondelete="cascade"),
            nullable=False,
        )


class User(SQLAlchemyBaseUserTable[int], Base):
    __tablename__ = "users"

    id = mapped_column(sqlalchemy.Integer, primary_key=True)
    username = mapped_column(sqlalchemy.TEXT, nullable=True)
    first_name = mapped_column(sqlalchemy.String(320), nullable=True)
    last_name = mapped_column(sqlalchemy.String(320), nullable=True)
    # Override SQLAlchemyBaseUserTable email attribute to keep current type
    email = mapped_column(
        sqlalchemy.TEXT,
        unique=True,
        index=True,
        nullable=False,
    )
    hashed_password: str = mapped_column(
        sqlalchemy.String(length=1024),
        nullable=True,
    )
    roles = relationship("UserRole", secondary=UserRoleMapping)
    teams = relationship(
        "Team", secondary=TeamUserMapping, back_populates="members"
    )
    oauth_accounts = relationship("UserOauthAccount", lazy="joined")


class Team(PermissionsMixin, Base):
    __tablename__ = "teams"

    id = mapped_column(sqlalchemy.Integer, primary_key=True)
    name = mapped_column(sqlalchemy.Text, nullable=False, unique=True)
    members = relationship(
        "User", secondary=TeamUserMapping, back_populates="teams"
    )
    products = relationship("Product", back_populates="team")
    roles = relationship(
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

    id = mapped_column(sqlalchemy.Integer, primary_key=True)
    name = mapped_column(sqlalchemy.Text, nullable=False, unique=True)
    # FIXME: change nullable to False after population
    title = mapped_column(sqlalchemy.String(100), nullable=True)
    description = mapped_column(sqlalchemy.Text, nullable=True)
    team = relationship("Team", back_populates="products")
    is_community = mapped_column(
        sqlalchemy.Boolean, nullable=False, default=True
    )
    roles = relationship("UserRole", secondary=ProductRoleMapping)
    repositories = relationship(
        "Repository",
        secondary=ProductRepositories,
        cascade="all, delete",
    )
    platforms = relationship(
        "Platform",
        secondary=ProductPlatforms,
    )
    builds = relationship(
        "Build",
        secondary=ProductBuilds,
        back_populates="products",
    )
    sign_keys = relationship(
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

    id = mapped_column(sqlalchemy.Integer, primary_key=True)
    package_name = mapped_column(sqlalchemy.TEXT, nullable=False)
    package_version = mapped_column(sqlalchemy.TEXT, nullable=False)
    package_release = mapped_column(sqlalchemy.TEXT, nullable=True)
    env_arch = mapped_column(sqlalchemy.TEXT, nullable=False)
    build_task_id = mapped_column(
        sqlalchemy.Integer,
        sqlalchemy.ForeignKey("build_tasks.id"),
        nullable=False,
        index=True,
    )
    build_task = relationship("BuildTask", back_populates="test_tasks")
    status = mapped_column(
        sqlalchemy.Integer,
        nullable=False,
        index=True,
    )
    alts_response = mapped_column(JSONB, nullable=True)
    revision = mapped_column(
        sqlalchemy.Integer,
        nullable=False,
        index=True,
    )
    artifacts = relationship("TestTaskArtifact", back_populates="test_task")
    repository_id = mapped_column(
        sqlalchemy.Integer,
        sqlalchemy.ForeignKey("repositories.id", name="test_task_repo_fk"),
        nullable=True,
    )
    repository = relationship("Repository")
    scheduled_at = mapped_column(sqlalchemy.DateTime, nullable=True)
    performance_stats: "PerformanceStats" = relationship(
        "PerformanceStats",
        back_populates="test_task",
    )


class TestTaskArtifact(Base):
    __tablename__ = "test_task_artifacts"
    id = mapped_column(sqlalchemy.Integer, primary_key=True)
    test_task_id = mapped_column(
        sqlalchemy.Integer,
        sqlalchemy.ForeignKey("test_tasks.id"),
        nullable=False,
    )
    test_task = relationship("TestTask", back_populates="artifacts")
    name = mapped_column(sqlalchemy.Text, nullable=False)
    href = mapped_column(sqlalchemy.Text, nullable=False)


class PackageTestRepository(Base):
    __tablename__ = "package_test_repository"
    __tableargs__ = [
        sqlalchemy.UniqueConstraint(
            "package_name",
            "folder_name",
            name="package_test_repo_uix",
        ),
    ]
    id = mapped_column(sqlalchemy.Integer, primary_key=True)
    package_name = mapped_column(sqlalchemy.Text, nullable=False)
    folder_name = mapped_column(sqlalchemy.Text, nullable=False)
    url = mapped_column(sqlalchemy.Text, nullable=False)
    test_repository_id = mapped_column(
        sqlalchemy.Integer,
        sqlalchemy.ForeignKey(
            "test_repositories.id",
            ondelete="CASCADE",
            name="fk_package_test_repository_id",
        ),
        nullable=False,
    )
    test_repository = relationship("TestRepository", back_populates="packages")


class TestRepository(Base):
    __tablename__ = "test_repositories"
    id = mapped_column(sqlalchemy.Integer, primary_key=True)
    name = mapped_column(sqlalchemy.Text, nullable=False, unique=True)
    url = mapped_column(sqlalchemy.Text, nullable=False, unique=True)
    tests_dir = mapped_column(sqlalchemy.Text, nullable=False)
    tests_prefix = mapped_column(sqlalchemy.Text, nullable=True)
    packages: List["PackageTestRepository"] = relationship(
        "PackageTestRepository",
        back_populates="test_repository",
        cascade="all, delete",
    )


class Release(PermissionsMixin, TeamMixin, TimeMixin, Base):
    __tablename__ = "build_releases"

    id = mapped_column(sqlalchemy.Integer, primary_key=True)
    build_ids = mapped_column(
        sqlalchemy.ARRAY(sqlalchemy.Integer, dimensions=1), nullable=False
    )
    created_at = mapped_column(
        sqlalchemy.DateTime,
        nullable=True,
        default=func.current_timestamp(),
    )
    build_task_ids = mapped_column(
        sqlalchemy.ARRAY(sqlalchemy.Integer, dimensions=1), nullable=True
    )
    reference_platform_id = mapped_column(
        sqlalchemy.Integer,
        nullable=True,
    )
    platform_id = mapped_column(
        sqlalchemy.Integer,
        sqlalchemy.ForeignKey("platforms.id"),
        nullable=False,
    )
    platform = relationship("Platform")
    product_id = mapped_column(
        sqlalchemy.Integer,
        sqlalchemy.ForeignKey(
            "products.id",
            name="build_releases_product_id_fkey",
        ),
        nullable=False,
    )
    product = relationship("Product")
    plan = mapped_column(JSONB, nullable=True)
    status = mapped_column(sqlalchemy.Integer, default=ReleaseStatus.SCHEDULED)
    performance_stats: List["PerformanceStats"] = relationship(
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

    id = mapped_column(sqlalchemy.Integer, primary_key=True)
    name = mapped_column(sqlalchemy.Text)
    # FIXME: change nullable to False after population
    is_community = mapped_column(
        sqlalchemy.Boolean,
        nullable=True,
        default=False,
    )
    description = mapped_column(sqlalchemy.Text, nullable=True)
    keyid = mapped_column(sqlalchemy.String(16), unique=True)
    fingerprint = mapped_column(sqlalchemy.String(40), unique=True)
    public_url = mapped_column(sqlalchemy.Text)
    inserted = mapped_column(
        sqlalchemy.DateTime, default=datetime.datetime.utcnow()
    )
    product_id = mapped_column(
        sqlalchemy.Integer,
        sqlalchemy.ForeignKey(
            'products.id',
            name='sign_keys_product_id_fkey',
        ),
        nullable=True,
    )
    product = relationship('Product', back_populates='sign_keys')
    platform_id = mapped_column(
        sqlalchemy.Integer,
        sqlalchemy.ForeignKey(
            "platforms.id",
            name="sign_keys_platform_id_fkey",
        ),
        nullable=True,
    )
    platform = relationship("Platform", back_populates="sign_keys")
    build_task_artifacts = relationship(
        "BuildTaskArtifact",
        back_populates="sign_key",
    )
    roles = relationship("UserRole", secondary=SignKeyRoleMapping)


class GenKeyTask(Base):
    __tablename__ = "gen_key_tasks"

    id = mapped_column(sqlalchemy.Integer, primary_key=True)
    status = mapped_column(sqlalchemy.Integer, default=GenKeyStatus.IDLE)
    error_message = mapped_column(sqlalchemy.Text, nullable=True)
    product = relationship("Product")
    product_id = mapped_column(
        sqlalchemy.Integer,
        sqlalchemy.ForeignKey("products.id"),
        nullable=False,
    )


class SignTask(TimeMixin, Base):
    __tablename__ = "sign_tasks"

    id = mapped_column(sqlalchemy.Integer, primary_key=True)
    build_id = mapped_column(
        sqlalchemy.Integer, sqlalchemy.ForeignKey("builds.id"), nullable=False
    )
    build = relationship("Build")
    sign_key_id = mapped_column(
        sqlalchemy.Integer,
        sqlalchemy.ForeignKey("sign_keys.id"),
        nullable=False,
    )
    sign_key = relationship("SignKey")
    status = mapped_column(sqlalchemy.Integer, default=SignStatus.IDLE)
    ts = mapped_column(sqlalchemy.DateTime, nullable=True)
    error_message = mapped_column(sqlalchemy.Text, nullable=True)
    log_href = mapped_column(sqlalchemy.Text, nullable=True)
    stats = mapped_column(JSONB, nullable=True)


class ExportTask(Base):
    __tablename__ = "export_tasks"

    id = mapped_column(sqlalchemy.Integer, primary_key=True)
    name = mapped_column(sqlalchemy.Text, nullable=False)
    status = mapped_column(sqlalchemy.Integer, nullable=False)
    exported_at = mapped_column(sqlalchemy.DateTime, nullable=True)


class RepoExporter(Base):
    __tablename__ = "repo_exporters"

    id = mapped_column(sqlalchemy.Integer, primary_key=True)
    path = mapped_column(sqlalchemy.Text, nullable=False)
    exported_id = mapped_column(
        sqlalchemy.Integer,
        sqlalchemy.ForeignKey("export_tasks.id"),
        nullable=False,
    )
    repository_id = mapped_column(
        sqlalchemy.Integer,
        sqlalchemy.ForeignKey("repositories.id"),
        nullable=False,
    )
    repository = relationship("Repository")
    fs_exporter_href = mapped_column(sqlalchemy.Text, nullable=False)


class PlatformFlavour(PermissionsMixin, Base):
    __tablename__ = "platform_flavours"

    id = mapped_column(sqlalchemy.Integer, primary_key=True)
    name = mapped_column(sqlalchemy.Text, nullable=False, unique=True)
    modularity = mapped_column(JSONB, nullable=True)
    repos = relationship("Repository", secondary=FlavourRepo)
    data = mapped_column(JSONB, nullable=True)


class NewErrataRecord(Base):
    __tablename__ = "new_errata_records"
    id = mapped_column(sqlalchemy.Text, primary_key=True)
    platform_id = mapped_column(
        sqlalchemy.Integer,
        sqlalchemy.ForeignKey(
            "platforms.id",
            name="new_errata_records_platform_id_fkey",
        ),
        nullable=False,
        primary_key=True,
    )
    platform = relationship("Platform")
    module = mapped_column(sqlalchemy.Text, nullable=True)
    release_status = mapped_column(
        sqlalchemy.Enum(ErrataReleaseStatus, name='erratareleasestatus'),
        nullable=False,
    )
    last_release_log = mapped_column(sqlalchemy.Text, nullable=True)
    summary = mapped_column(sqlalchemy.Text, nullable=True)
    solution = mapped_column(sqlalchemy.Text, nullable=True)

    freezed = mapped_column(sqlalchemy.Boolean, nullable=True)

    issued_date = mapped_column(sqlalchemy.DateTime, nullable=False)
    updated_date = mapped_column(sqlalchemy.DateTime, nullable=False)
    description = mapped_column(sqlalchemy.Text, nullable=True)
    original_description = mapped_column(sqlalchemy.Text, nullable=False)
    title = mapped_column(sqlalchemy.Text, nullable=True)
    oval_title = mapped_column(sqlalchemy.Text, nullable=True)
    original_title = mapped_column(sqlalchemy.Text, nullable=False)
    contact_mail = mapped_column(sqlalchemy.Text, nullable=False)
    status = mapped_column(sqlalchemy.Text, nullable=False)
    version = mapped_column(sqlalchemy.Text, nullable=False)
    severity = mapped_column(sqlalchemy.Text, nullable=False)
    rights = mapped_column(sqlalchemy.Text, nullable=False)
    # OVAL-only fields
    definition_id = mapped_column(sqlalchemy.Text, nullable=False)
    definition_version = mapped_column(sqlalchemy.Text, nullable=False)
    definition_class = mapped_column(sqlalchemy.Text, nullable=False)
    affected_cpe = mapped_column(JSONB, nullable=False, default=[])
    criteria = mapped_column(JSONB, nullable=True)
    original_criteria = mapped_column(JSONB, nullable=True)
    tests = mapped_column(JSONB, nullable=True)
    original_tests = mapped_column(JSONB, nullable=True)
    objects = mapped_column(JSONB, nullable=True)
    original_objects = mapped_column(JSONB, nullable=True)
    states = mapped_column(JSONB, nullable=True)
    original_states = mapped_column(JSONB, nullable=True)
    variables = mapped_column(JSONB, nullable=True)
    original_variables = mapped_column(JSONB, nullable=True)

    references = relationship(
        "NewErrataReference",
        back_populates="platform_specific_errata_record",
    )
    packages = relationship(
        "NewErrataPackage",
        back_populates="platform_specific_errata_record",
    )

    cves = association_proxy("references", "cve_id")

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

    id = mapped_column(sqlalchemy.Integer, primary_key=True)
    errata_record_id = mapped_column(sqlalchemy.Text)
    platform_id = mapped_column(sqlalchemy.Integer)
    platform_specific_errata_record = relationship(
        "NewErrataRecord",
        foreign_keys=[errata_record_id, platform_id],
        cascade="all, delete",
        primaryjoin="and_(NewErrataPackage.errata_record_id == NewErrataRecord.id,"
        "NewErrataPackage.platform_id == NewErrataRecord.platform_id)",
        back_populates="packages",
    )
    name = mapped_column(sqlalchemy.Text, nullable=False)
    version = mapped_column(sqlalchemy.Text, nullable=False)
    release = mapped_column(sqlalchemy.Text, nullable=False)
    epoch = mapped_column(sqlalchemy.Integer, nullable=False)
    arch = mapped_column(sqlalchemy.Text, nullable=False)
    source_srpm = mapped_column(sqlalchemy.Text, nullable=True)
    reboot_suggested = mapped_column(sqlalchemy.Boolean, nullable=False)
    albs_packages = relationship(
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

    id = mapped_column(sqlalchemy.Integer, primary_key=True)
    href = mapped_column(sqlalchemy.Text, nullable=False)
    ref_id = mapped_column(sqlalchemy.Text, nullable=False)
    title = mapped_column(sqlalchemy.Text, nullable=False)
    ref_type = mapped_column(
        sqlalchemy.Enum(ErrataReferenceType), nullable=False
    )
    errata_record_id = mapped_column(sqlalchemy.Text)
    platform_id = mapped_column(sqlalchemy.Integer)
    platform_specific_errata_record = relationship(
        "NewErrataRecord",
        foreign_keys=[errata_record_id, platform_id],
        cascade="all, delete",
        primaryjoin="and_(NewErrataReference.errata_record_id == NewErrataRecord.id,"
        "NewErrataReference.platform_id == NewErrataRecord.platform_id)",
        back_populates="references",
    )
    cve = relationship("ErrataCVE", cascade="all, delete")
    cve_id = mapped_column(
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

    id = mapped_column(sqlalchemy.Integer, primary_key=True)
    errata_package_id = mapped_column(
        sqlalchemy.Integer,
        sqlalchemy.ForeignKey(
            "new_errata_packages.id",
            name="new_errata_to_albs_package_errata_package_id_fk",
            ondelete="CASCADE",
        ),
        nullable=False,
        index=True,
    )
    errata_package = relationship(
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
    build_artifact: BuildTaskArtifact = relationship("BuildTaskArtifact")
    pulp_href = mapped_column(sqlalchemy.Text, nullable=True)
    status = mapped_column(
        sqlalchemy.Enum(ErrataPackageStatus),
        nullable=False,
    )

    name = mapped_column(sqlalchemy.Text, nullable=False)
    arch = mapped_column(sqlalchemy.Text, nullable=False)
    version = mapped_column(sqlalchemy.Text, nullable=False)
    release = mapped_column(sqlalchemy.Text, nullable=False)
    epoch = mapped_column(sqlalchemy.Integer, nullable=False)

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

    id = mapped_column(sqlalchemy.Text, primary_key=True)
    platform_id = mapped_column(
        sqlalchemy.Integer,
        sqlalchemy.ForeignKey("platforms.id"),
        nullable=False,
    )
    platform = relationship("Platform")
    module = mapped_column(sqlalchemy.Text, nullable=True)
    release_status = mapped_column(
        sqlalchemy.Enum(ErrataReleaseStatus),
        nullable=True,
    )
    last_release_log = mapped_column(sqlalchemy.Text, nullable=True)
    summary = mapped_column(sqlalchemy.Text, nullable=True)
    solution = mapped_column(sqlalchemy.Text, nullable=True)

    freezed = mapped_column(sqlalchemy.Boolean, nullable=True)

    issued_date = mapped_column(sqlalchemy.DateTime, nullable=False)
    updated_date = mapped_column(sqlalchemy.DateTime, nullable=False)
    description = mapped_column(sqlalchemy.Text, nullable=True)
    original_description = mapped_column(sqlalchemy.Text, nullable=False)
    title = mapped_column(sqlalchemy.Text, nullable=True)
    oval_title = mapped_column(sqlalchemy.Text, nullable=True)
    original_title = mapped_column(sqlalchemy.Text, nullable=False)
    contact_mail = mapped_column(sqlalchemy.Text, nullable=False)
    status = mapped_column(sqlalchemy.Text, nullable=False)
    version = mapped_column(sqlalchemy.Text, nullable=False)
    severity = mapped_column(sqlalchemy.Text, nullable=False)
    rights = mapped_column(sqlalchemy.Text, nullable=False)
    # OVAL-only fields
    definition_id = mapped_column(sqlalchemy.Text, nullable=False)
    definition_version = mapped_column(sqlalchemy.Text, nullable=False)
    definition_class = mapped_column(sqlalchemy.Text, nullable=False)
    affected_cpe = mapped_column(JSONB, nullable=False, default=[])
    criteria = mapped_column(JSONB, nullable=True)
    original_criteria = mapped_column(JSONB, nullable=True)
    tests = mapped_column(JSONB, nullable=True)
    original_tests = mapped_column(JSONB, nullable=True)
    objects = mapped_column(JSONB, nullable=True)
    original_objects = mapped_column(JSONB, nullable=True)
    states = mapped_column(JSONB, nullable=True)
    original_states = mapped_column(JSONB, nullable=True)
    variables = mapped_column(JSONB, nullable=True)
    original_variables = mapped_column(JSONB, nullable=True)

    references = relationship("ErrataReference", cascade="all, delete")
    packages = relationship("ErrataPackage", cascade="all, delete")

    cves = association_proxy("references", "cve_id")

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

    id = mapped_column(sqlalchemy.Integer, primary_key=True)
    href = mapped_column(sqlalchemy.Text, nullable=False)
    ref_id = mapped_column(sqlalchemy.Text, nullable=False)
    title = mapped_column(sqlalchemy.Text, nullable=False)
    ref_type = mapped_column(
        sqlalchemy.Enum(ErrataReferenceType), nullable=False
    )
    errata_record_id = mapped_column(
        sqlalchemy.Text,
        sqlalchemy.ForeignKey(
            "errata_records.id",
            name="errata_reference_errata_record_id_fk",
            ondelete="CASCADE",
        ),
        nullable=False,
        index=True,
    )
    cve = relationship("ErrataCVE", cascade="all, delete")
    cve_id = mapped_column(
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

    id = mapped_column(sqlalchemy.Text, primary_key=True)
    cvss3 = mapped_column(sqlalchemy.Text, nullable=False)
    cwe = mapped_column(sqlalchemy.Text, nullable=True)
    impact = mapped_column(sqlalchemy.Text, nullable=True)
    public = mapped_column(sqlalchemy.Text, nullable=False)


class ErrataPackage(Base):
    __tablename__ = "errata_packages"

    id = mapped_column(sqlalchemy.Integer, primary_key=True)
    errata_record_id = mapped_column(
        sqlalchemy.Text,
        sqlalchemy.ForeignKey(
            "errata_records.id",
            name="errata_package_errata_record_id_fk",
            ondelete="CASCADE",
        ),
        nullable=False,
        index=True,
    )
    name = mapped_column(sqlalchemy.Text, nullable=False)
    version = mapped_column(sqlalchemy.Text, nullable=False)
    release = mapped_column(sqlalchemy.Text, nullable=False)
    epoch = mapped_column(sqlalchemy.Integer, nullable=False)
    arch = mapped_column(sqlalchemy.Text, nullable=False)
    source_srpm = mapped_column(sqlalchemy.Text, nullable=True)
    reboot_suggested = mapped_column(sqlalchemy.Boolean, nullable=False)
    albs_packages = relationship(
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

    id = mapped_column(sqlalchemy.Integer, primary_key=True)
    errata_package_id = mapped_column(
        sqlalchemy.Integer,
        sqlalchemy.ForeignKey(
            "errata_packages.id",
            name="errata_to_albs_package_errata_package_id_fk",
            ondelete="CASCADE",
        ),
        nullable=False,
        index=True,
    )
    errata_package = relationship(
        "ErrataPackage",
        back_populates="albs_packages",
    )
    albs_artifact_id = mapped_column(
        sqlalchemy.Integer,
        sqlalchemy.ForeignKey(
            "build_artifacts.id",
            name="errata_to_albs_packages_albs_artifact_id_fkey",
            ondelete="CASCADE",
        ),
        nullable=True,
    )
    build_artifact: BuildTaskArtifact = relationship("BuildTaskArtifact")
    pulp_href = mapped_column(sqlalchemy.Text, nullable=True)
    status = mapped_column(
        sqlalchemy.Enum(ErrataPackageStatus),
        nullable=False,
    )

    name = mapped_column(sqlalchemy.Text, nullable=False)
    arch = mapped_column(sqlalchemy.Text, nullable=False)
    version = mapped_column(sqlalchemy.Text, nullable=False)
    release = mapped_column(sqlalchemy.Text, nullable=False)
    epoch = mapped_column(sqlalchemy.Integer, nullable=False)

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

    id: int = mapped_column(sqlalchemy.Integer, primary_key=True)
    statistics: Dict[str, Dict[str, Dict[str, str]]] = mapped_column(
        JSONB,
        nullable=True,
    )
    build_task_id: int = mapped_column(
        sqlalchemy.Integer,
        sqlalchemy.ForeignKey(
            "build_tasks.id",
            name="perf_stats_build_task_id",
        ),
        nullable=True,
        index=True,
    )
    build_task: BuildTask = relationship(
        "BuildTask",
        back_populates="performance_stats",
    )
    test_task_id: int = mapped_column(
        sqlalchemy.Integer,
        sqlalchemy.ForeignKey("test_tasks.id", name="perf_stats_test_task_id"),
        nullable=True,
        index=True,
    )
    test_task: TestTask = relationship(
        "TestTask",
        back_populates="performance_stats",
    )
    release_id: int = mapped_column(
        sqlalchemy.Integer,
        sqlalchemy.ForeignKey(
            "build_releases.id",
            name="perf_stats_build_release_id",
        ),
        nullable=True,
        index=True,
    )
    release: Release = relationship(
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
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


if __name__ == "__main__":
    asyncio.run(create_tables())

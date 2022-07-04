import asyncio
import datetime
import enum
import re

import sqlalchemy
from sqlalchemy.orm import relationship, declared_attr, declarative_mixin
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.associationproxy import association_proxy

from alws.constants import (
    Permissions,
    PermissionTriad,
    ReleaseStatus,
    SignStatus,
)
from alws.database import Base, engine


__all__ = [
    'Build',
    'BuildTask',
    'Distribution',
    'Platform',
    'SignKey',
    'SignTask',
    'User',
    'UserAction',
    'UserRole',
    'Team',
]


@declarative_mixin
class TeamMixin:

    @declared_attr
    def team_id(cls):
        # FIXME: Change nullable to False after owner population
        return sqlalchemy.Column(
            sqlalchemy.Integer, sqlalchemy.ForeignKey(
                'teams.id', name=f'{cls.__tablename__}_team_id_fkey'),
            nullable=True)

    @declared_attr
    def team(cls):
        return relationship('Team')


@declarative_mixin
class PermissionsMixin:

    @declared_attr
    def owner_id(cls):
        # FIXME: Change nullable to False after owner population
        return sqlalchemy.Column(
            sqlalchemy.Integer, sqlalchemy.ForeignKey(
                'users.id', name=f'{cls.__tablename__}_owner_id_fkey'),
            nullable=True)

    @declared_attr
    def owner(cls):
        return relationship('User')

    permissions = sqlalchemy.Column(sqlalchemy.Integer, nullable=False,
                                    default=764)

    @property
    def permissions_triad(self):
        self.validate_permissions(self.permissions)
        return PermissionTriad(
            Permissions(self.permissions // 100),
            Permissions(self.permissions // 10 % 10),
            Permissions(self.permissions % 10),
        )

    @staticmethod
    def validate_permissions(permissions: int):
        if len(str(permissions)) != 3:
            raise ValueError(
                'Incorrect permissions set, should be a string of 3 digits')
        test = permissions
        while test > 0:
            if test % 10 > 7:
                raise ValueError('Incorrect permissions representation')
            test //= 10
        return permissions


PlatformRepo = sqlalchemy.Table(
    'platform_repository',
    Base.metadata,
    sqlalchemy.Column(
        'platform_id',
        sqlalchemy.Integer,
        sqlalchemy.ForeignKey('platforms.id'),
        primary_key=True
    ),
    sqlalchemy.Column(
        'repository_id',
        sqlalchemy.Integer,
        sqlalchemy.ForeignKey('repositories.id'),
        primary_key=True
    )
)

FlavourRepo = sqlalchemy.Table(
    'platform_flavour_repository',
    Base.metadata,
    sqlalchemy.Column(
        'flavour_id',
        sqlalchemy.Integer,
        sqlalchemy.ForeignKey('platform_flavours.id'),
        primary_key=True
    ),
    sqlalchemy.Column(
        'repository_id',
        sqlalchemy.Integer,
        sqlalchemy.ForeignKey('repositories.id'),
        primary_key=True
    )
)

BuildPlatformFlavour = sqlalchemy.Table(
    'build_platform_flavour',
    Base.metadata,
    sqlalchemy.Column(
        'flavour_id',
        sqlalchemy.Integer,
        sqlalchemy.ForeignKey('platform_flavours.id'),
        primary_key=True
    ),
    sqlalchemy.Column(
        'build_id',
        sqlalchemy.Integer,
        sqlalchemy.ForeignKey('builds.id'),
        primary_key=True
    )
)

PlatformDependency = sqlalchemy.Table(
    'platform_dependency',
    Base.metadata,
    sqlalchemy.Column(
        'distribution_id',
        sqlalchemy.Integer,
        sqlalchemy.ForeignKey('distributions.id'),
        primary_key=True
    ),
    sqlalchemy.Column(
        'platform_id',
        sqlalchemy.Integer,
        sqlalchemy.ForeignKey('platforms.id'),
        primary_key=True
    )
)


DistributionRepositories = sqlalchemy.Table(
    'distribution_repositories',
    Base.metadata,
    sqlalchemy.Column(
        'distribution_id',
        sqlalchemy.Integer,
        sqlalchemy.ForeignKey('distributions.id'),
        primary_key=True
    ),
    sqlalchemy.Column(
        'repository_id',
        sqlalchemy.Integer,
        sqlalchemy.ForeignKey('repositories.id'),
        primary_key=True
    )
)


DistributionBuilds = sqlalchemy.Table(
    'distribution_packages',
    Base.metadata,
    sqlalchemy.Column(
        'distribution_id',
        sqlalchemy.Integer,
        sqlalchemy.ForeignKey('distributions.id'),
        primary_key=True
    ),
    sqlalchemy.Column(
        'build_id',
        sqlalchemy.Integer,
        sqlalchemy.ForeignKey('builds.id'),
        primary_key=True
    )
)


ReferencePlatforms = sqlalchemy.Table(
    'reference_platforms',
    Base.metadata,
    sqlalchemy.Column(
        'platform_id',
        sqlalchemy.Integer,
        sqlalchemy.ForeignKey('platforms.id'),
        primary_key=True,
    ),
    sqlalchemy.Column(
        'refefence_platform_id',
        sqlalchemy.Integer,
        sqlalchemy.ForeignKey('platforms.id'),
        primary_key=True,
    ),
)


class Platform(PermissionsMixin, Base):

    __tablename__ = 'platforms'

    id = sqlalchemy.Column(sqlalchemy.Integer, primary_key=True)
    contact_mail = sqlalchemy.Column(sqlalchemy.Text, nullable=True)
    copyright = sqlalchemy.Column(sqlalchemy.Text, nullable=True)
    type = sqlalchemy.Column(sqlalchemy.Text, nullable=False)
    distr_type = sqlalchemy.Column(sqlalchemy.Text, nullable=False)
    distr_version = sqlalchemy.Column(sqlalchemy.Text, nullable=False)
    module_build_index = sqlalchemy.Column(sqlalchemy.Integer, default=1)
    modularity = sqlalchemy.Column(JSONB, nullable=True)
    test_dist_name = sqlalchemy.Column(sqlalchemy.Text, nullable=False)
    name = sqlalchemy.Column(
        sqlalchemy.Text,
        nullable=False,
        unique=True,
        index=True
    )
    priority = sqlalchemy.Column(sqlalchemy.Integer, nullable=True)
    arch_list = sqlalchemy.Column(JSONB, nullable=False)
    copy_priority_arches = sqlalchemy.Column(JSONB, nullable=True)
    weak_arch_list = sqlalchemy.Column(JSONB, nullable=True)
    data = sqlalchemy.Column(JSONB, nullable=False)
    is_reference = sqlalchemy.Column(
        sqlalchemy.Boolean, default=False, nullable=True)
    reference_platforms = relationship(
        'Platform',
        secondary=ReferencePlatforms,
        primaryjoin=(ReferencePlatforms.c.platform_id == id),
        secondaryjoin=(ReferencePlatforms.c.refefence_platform_id == id),
    )
    repos = relationship('Repository', secondary=PlatformRepo)
    sign_keys = relationship('SignKey', back_populates='platform')


class Distribution(PermissionsMixin, TeamMixin, Base):

    __tablename__ = 'distributions'

    id = sqlalchemy.Column(sqlalchemy.Integer, primary_key=True)
    name = sqlalchemy.Column(
        sqlalchemy.Text,
        nullable=False,
        unique=True,
        index=True
    )
    platforms = relationship('Platform', secondary=PlatformDependency)
    repositories = relationship('Repository', secondary=DistributionRepositories)
    builds = relationship('Build', secondary=DistributionBuilds)


class CustomRepoRepr(Base):
    __abstract__ = True

    def __repr__(self):
        return f'{self.__class__.__name__}: {self.name} {self.arch} {self.url}'


class Repository(CustomRepoRepr, PermissionsMixin):

    __tablename__ = 'repositories'
    __table_args__ = (
        sqlalchemy.UniqueConstraint(
            'name', 'arch', 'type', 'debug', name='repos_uix'),
    )

    id = sqlalchemy.Column(sqlalchemy.Integer, primary_key=True)
    name = sqlalchemy.Column(sqlalchemy.Text, nullable=False)
    arch = sqlalchemy.Column(sqlalchemy.Text, nullable=False)
    url = sqlalchemy.Column(sqlalchemy.Text, nullable=False)
    type = sqlalchemy.Column(sqlalchemy.Text, nullable=False)
    debug = sqlalchemy.Column(sqlalchemy.Boolean, default=False)
    production = sqlalchemy.Column(sqlalchemy.Boolean, default=False,
                                   nullable=True)
    pulp_href = sqlalchemy.Column(sqlalchemy.Text)
    export_path = sqlalchemy.Column(sqlalchemy.Text, nullable=True)
    priority = sqlalchemy.Column(sqlalchemy.Integer, default=10,
                                 nullable=False)


class RepositoryRemote(CustomRepoRepr):
    __tablename__ = 'repository_remotes'
    __tableargs__ = [
        sqlalchemy.UniqueConstraint('name', 'arch', 'url', name='repo_remote_uix')
    ]

    id = sqlalchemy.Column(sqlalchemy.Integer, primary_key=True)
    name = sqlalchemy.Column(sqlalchemy.Text, nullable=False)
    arch = sqlalchemy.Column(sqlalchemy.Text, nullable=True)
    url = sqlalchemy.Column(sqlalchemy.Text, nullable=False)
    pulp_href = sqlalchemy.Column(sqlalchemy.Text, nullable=False)


BuildRepo = sqlalchemy.Table(
    'build_repo',
    Base.metadata,
    sqlalchemy.Column(
        'build_id',
        sqlalchemy.Integer,
        sqlalchemy.ForeignKey('builds.id'),
        primary_key=True
    ),
    sqlalchemy.Column(
        'repository_id',
        sqlalchemy.Integer,
        sqlalchemy.ForeignKey('repositories.id'),
        primary_key=True
    )
)


BuildDependency = sqlalchemy.Table(
    'build_dependency',
    Base.metadata,
    sqlalchemy.Column(
        'build_id',
        sqlalchemy.Integer,
        sqlalchemy.ForeignKey('builds.id'),
        primary_key=True
    ),
    sqlalchemy.Column(
        'build_dependency',
        sqlalchemy.Integer,
        sqlalchemy.ForeignKey('builds.id'),
        primary_key=True
    )
)


class Build(PermissionsMixin, TeamMixin, Base):

    __tablename__ = 'builds'

    id = sqlalchemy.Column(sqlalchemy.Integer, primary_key=True)
    created_at = sqlalchemy.Column(
        sqlalchemy.DateTime,
        nullable=False,
        # TODO: replace with sql function
        default=datetime.datetime.utcnow
    )
    tasks = relationship('BuildTask', back_populates='build')
    sign_tasks = relationship('SignTask', back_populates='build',
                              order_by='SignTask.id')
    repos = relationship('Repository', secondary=BuildRepo)
    linked_builds = relationship(
        'Build',
        secondary=BuildDependency,
        primaryjoin=(BuildDependency.c.build_id == id),
        secondaryjoin=(BuildDependency.c.build_dependency == id)
    )
    mock_options = sqlalchemy.Column(JSONB)
    release_id = sqlalchemy.Column(
        sqlalchemy.Integer,
        sqlalchemy.ForeignKey('build_releases.id',
                              name='build_releases_id_fkey'),
        nullable=True
    )
    release = relationship('Release')
    source_rpms = relationship('SourceRpm', back_populates='build')
    binary_rpms = relationship('BinaryRpm', back_populates='build')
    platform_flavors = relationship(
        'PlatformFlavour', secondary=BuildPlatformFlavour
    )
    released = sqlalchemy.Column(sqlalchemy.Boolean, default=False)
    signed = sqlalchemy.Column(sqlalchemy.Boolean, default=False,
                               nullable=True)


BuildTaskDependency = sqlalchemy.Table(
    'build_task_dependency',
    Base.metadata,
    sqlalchemy.Column(
        'build_task_id',
        sqlalchemy.Integer,
        sqlalchemy.ForeignKey('build_tasks.id'),
        primary_key=True
    ),
    sqlalchemy.Column(
        'build_task_dependency',
        sqlalchemy.Integer,
        sqlalchemy.ForeignKey('build_tasks.id'),
        primary_key=True
    )
)


class BuildTask(Base):

    __tablename__ = 'build_tasks'

    id = sqlalchemy.Column(sqlalchemy.Integer, primary_key=True)
    ts = sqlalchemy.Column(sqlalchemy.DateTime, nullable=True)
    build_id = sqlalchemy.Column(
        sqlalchemy.Integer,
        sqlalchemy.ForeignKey('builds.id'),
        # saw https://stackoverflow.com/questions/
        # 5033547/sqlalchemy-cascade-delete
        nullable=False
    )
    platform_id = sqlalchemy.Column(
        sqlalchemy.Integer,
        sqlalchemy.ForeignKey('platforms.id'),
        nullable=False
    )
    ref_id = sqlalchemy.Column(
        sqlalchemy.Integer,
        sqlalchemy.ForeignKey('build_task_refs.id'),
        nullable=False
    )
    rpm_module_id = sqlalchemy.Column(
        sqlalchemy.Integer,
        sqlalchemy.ForeignKey('rpm_module.id'),
        nullable=True
    )
    status = sqlalchemy.Column(sqlalchemy.Integer, nullable=False)
    index = sqlalchemy.Column(sqlalchemy.Integer, nullable=False)
    arch = sqlalchemy.Column(sqlalchemy.VARCHAR(length=50), nullable=False)
    is_secure_boot = sqlalchemy.Column(
        sqlalchemy.Boolean, default=False, nullable=True)
    mock_options = sqlalchemy.Column(JSONB)
    ref = relationship('BuildTaskRef')
    alma_commit_cas_hash = sqlalchemy.Column(sqlalchemy.Text, nullable=True)
    is_cas_authenticated = sqlalchemy.Column(
        sqlalchemy.Boolean, default=False, nullable=True)
    artifacts = relationship('BuildTaskArtifact', back_populates='build_task')
    platform = relationship('Platform')
    build = relationship('Build', back_populates='tasks')
    dependencies = relationship(
        'BuildTask',
        secondary=BuildTaskDependency,
        primaryjoin=(BuildTaskDependency.c.build_task_id == id),
        secondaryjoin=(BuildTaskDependency.c.build_task_dependency == id)
    )
    test_tasks = relationship('TestTask', back_populates='build_task')
    rpm_module = relationship('RpmModule')
    built_srpm_url = sqlalchemy.Column(sqlalchemy.VARCHAR, nullable=True)
    error = sqlalchemy.Column(sqlalchemy.Text, nullable=True, default=None)

    def get_log_repo_name(self):
        return '-'.join([
            self.platform.name,
            self.arch,
            str(self.build_id),
            'artifacts',
            str(self.id)
        ])


class BuildTaskRef(Base):

    __tablename__ = 'build_task_refs'

    id = sqlalchemy.Column(sqlalchemy.Integer, primary_key=True)
    url = sqlalchemy.Column(sqlalchemy.TEXT, nullable=False)
    git_ref = sqlalchemy.Column(sqlalchemy.TEXT)
    ref_type = sqlalchemy.Column(sqlalchemy.Integer)
    git_commit_hash = sqlalchemy.Column(sqlalchemy.TEXT, nullable=True)


class RpmModule(Base):

    __tablename__ = 'rpm_module'

    id = sqlalchemy.Column(sqlalchemy.Integer, primary_key=True)
    name = sqlalchemy.Column(sqlalchemy.TEXT, nullable=False)
    version = sqlalchemy.Column(sqlalchemy.TEXT, nullable=False)
    stream = sqlalchemy.Column(sqlalchemy.TEXT, nullable=False)
    context = sqlalchemy.Column(sqlalchemy.TEXT, nullable=False)
    arch = sqlalchemy.Column(sqlalchemy.TEXT, nullable=False)
    pulp_href = sqlalchemy.Column(sqlalchemy.TEXT, nullable=False)
    sha256 = sqlalchemy.Column(sqlalchemy.VARCHAR(64), nullable=False)

    @property
    def nvsca(self):
        return (f'{self.name}-{self.version}-{self.stream}'
                f'-{self.context}-{self.arch}')


class BuildTaskArtifact(Base):

    __tablename__ = 'build_artifacts'

    id = sqlalchemy.Column(sqlalchemy.Integer, primary_key=True)
    build_task_id = sqlalchemy.Column(
        sqlalchemy.Integer,
        sqlalchemy.ForeignKey('build_tasks.id'),
        nullable=False
    )
    name = sqlalchemy.Column(sqlalchemy.Text, nullable=False)
    type = sqlalchemy.Column(sqlalchemy.Text, nullable=False)
    href = sqlalchemy.Column(sqlalchemy.Text, nullable=False)
    build_task = relationship('BuildTask', back_populates='artifacts')
    cas_hash = sqlalchemy.Column(sqlalchemy.Text, nullable=True)
    sign_key_id = sqlalchemy.Column(
        sqlalchemy.Integer,
        sqlalchemy.ForeignKey('sign_keys.id',
                              name='build_artifacts_sign_key_id_fkey'),
        nullable=True)
    sign_key = relationship('SignKey',
                            back_populates='build_task_artifacts')

    def name_as_dict(self) -> dict:
        result = re.search(
            r'^(?P<name>[\w+-.]+)-'
            r'(?P<version>\d+?[\w.]*)-'
            r'(?P<release>\d+?[\w.+]*?)'
            r'\.(?P<arch>[\w]*)(\.rpm)?$',
            self.name
        )
        if not result:
            return {}
        return result.groupdict()


class SourceRpm(Base):
    __tablename__ = 'source_rpms'

    id = sqlalchemy.Column(sqlalchemy.Integer, primary_key=True)
    build_id = sqlalchemy.Column(
        sqlalchemy.Integer,
        sqlalchemy.ForeignKey('builds.id'),
        nullable=False
    )
    build = relationship('Build', back_populates='source_rpms')
    artifact_id = sqlalchemy.Column(
        sqlalchemy.Integer,
        sqlalchemy.ForeignKey('build_artifacts.id'),
        nullable=False
    )
    artifact = relationship('BuildTaskArtifact')
    binary_rpms = relationship('BinaryRpm', back_populates='source_rpm')


class BinaryRpm(Base):
    __tablename__ = 'binary_rpms'

    id = sqlalchemy.Column(sqlalchemy.Integer, primary_key=True)
    build_id = sqlalchemy.Column(
        sqlalchemy.Integer,
        sqlalchemy.ForeignKey('builds.id'),
        nullable=False
    )
    build = relationship('Build', back_populates='binary_rpms')
    artifact_id = sqlalchemy.Column(
        sqlalchemy.Integer,
        sqlalchemy.ForeignKey('build_artifacts.id'),
        nullable=False
    )
    artifact = relationship('BuildTaskArtifact')
    source_rpm_id = sqlalchemy.Column(
        sqlalchemy.Integer,
        sqlalchemy.ForeignKey('source_rpms.id'),
        nullable=False
    )
    source_rpm = relationship('SourceRpm', back_populates='binary_rpms')


class UserAction(Base):

    __tablename__ = 'user_actions'

    id = sqlalchemy.Column(sqlalchemy.Integer, primary_key=True)
    name = sqlalchemy.Column(sqlalchemy.String(100), unique=True)
    description = sqlalchemy.Column(sqlalchemy.TEXT, nullable=True)


ActionRoleMapping = sqlalchemy.Table(
    'action_role_mapping',
    Base.metadata,
    sqlalchemy.Column(
        'action_id',
        sqlalchemy.Integer,
        sqlalchemy.ForeignKey('user_actions.id'),
        primary_key=True
    ),
    sqlalchemy.Column(
        'role_id',
        sqlalchemy.Integer,
        sqlalchemy.ForeignKey('user_roles.id'),
        primary_key=True
    )
)


class UserRole(Base):

    __tablename__ = 'user_roles'

    id = sqlalchemy.Column(sqlalchemy.Integer, primary_key=True)
    name = sqlalchemy.Column(sqlalchemy.String(100), unique=True)
    actions = relationship(
        'UserAction', secondary=ActionRoleMapping
    )

    def __repr__(self):
        return f'{self.__class__.__name__}: {self.id} {self.name}'


UserRoleMapping = sqlalchemy.Table(
    'user_role_mapping',
    Base.metadata,
    sqlalchemy.Column(
        'user_id',
        sqlalchemy.Integer,
        sqlalchemy.ForeignKey('users.id'),
        primary_key=True
    ),
    sqlalchemy.Column(
        'role_id',
        sqlalchemy.Integer,
        sqlalchemy.ForeignKey('user_roles.id'),
        primary_key=True
    )
)

ProductRoleMapping = sqlalchemy.Table(
    'product_role_mapping',
    Base.metadata,
    sqlalchemy.Column(
        'product_id',
        sqlalchemy.Integer,
        sqlalchemy.ForeignKey('products.id'),
        primary_key=True
    ),
    sqlalchemy.Column(
        'role_id',
        sqlalchemy.Integer,
        sqlalchemy.ForeignKey('user_roles.id'),
        primary_key=True
    )
)

TeamRoleMapping = sqlalchemy.Table(
    'team_role_mapping',
    Base.metadata,
    sqlalchemy.Column(
        'team_id',
        sqlalchemy.Integer,
        sqlalchemy.ForeignKey('teams.id'),
        primary_key=True
    ),
    sqlalchemy.Column(
        'role_id',
        sqlalchemy.Integer,
        sqlalchemy.ForeignKey('user_roles.id'),
        primary_key=True
    )
)

TeamUserMapping = sqlalchemy.Table(
    'team_user_mapping',
    Base.metadata,
    sqlalchemy.Column(
        'team_id',
        sqlalchemy.Integer,
        sqlalchemy.ForeignKey('teams.id'),
        primary_key=True
    ),
    sqlalchemy.Column(
        'user_id',
        sqlalchemy.Integer,
        sqlalchemy.ForeignKey('users.id'),
        primary_key=True
    )
)


class User(Base):

    __tablename__ = 'users'

    id = sqlalchemy.Column(sqlalchemy.Integer, primary_key=True)
    username = sqlalchemy.Column(sqlalchemy.TEXT, nullable=False)
    email = sqlalchemy.Column(sqlalchemy.TEXT, nullable=False)
    jwt_token = sqlalchemy.Column(sqlalchemy.TEXT)
    github_token = sqlalchemy.Column(sqlalchemy.TEXT)
    roles = relationship(
        'UserRole', secondary=UserRoleMapping
    )
    teams = relationship(
        'Team', secondary=TeamUserMapping, back_populates='members'
    )


class Team(PermissionsMixin, Base):
    __tablename__ = 'teams'

    id = sqlalchemy.Column(sqlalchemy.Integer, primary_key=True)
    name = sqlalchemy.Column(sqlalchemy.Text, nullable=False, unique=True)
    members = relationship(
        'User', secondary=TeamUserMapping, back_populates='teams'
    )
    products = relationship('Product', back_populates='team')
    roles = relationship(
        'UserRole', secondary=TeamRoleMapping
    )


class Product(PermissionsMixin, TeamMixin, Base):

    __tablename__ = 'products'

    id = sqlalchemy.Column(sqlalchemy.Integer, primary_key=True)
    name = sqlalchemy.Column(sqlalchemy.Text, nullable=False, unique=True)
    team = relationship('Team', back_populates='products')
    roles = relationship(
        'UserRole', secondary=ProductRoleMapping
    )


class TestTask(Base):

    __tablename__ = 'test_tasks'

    id = sqlalchemy.Column(sqlalchemy.Integer, primary_key=True)
    package_name = sqlalchemy.Column(sqlalchemy.TEXT, nullable=False)
    package_version = sqlalchemy.Column(sqlalchemy.TEXT, nullable=False)
    package_release = sqlalchemy.Column(sqlalchemy.TEXT, nullable=True)
    env_arch = sqlalchemy.Column(sqlalchemy.TEXT, nullable=False)
    build_task_id = sqlalchemy.Column(
        sqlalchemy.Integer,
        sqlalchemy.ForeignKey('build_tasks.id'),
        nullable=False
    )
    build_task = relationship('BuildTask', back_populates='test_tasks')
    status = sqlalchemy.Column(sqlalchemy.Integer, nullable=False)
    alts_response = sqlalchemy.Column(JSONB, nullable=True)
    revision = sqlalchemy.Column(sqlalchemy.Integer, nullable=False)
    artifacts = relationship('TestTaskArtifact', back_populates='test_task')
    repository_id = sqlalchemy.Column(
        sqlalchemy.Integer,
        sqlalchemy.ForeignKey('repositories.id', name='test_task_repo_fk'),
        nullable=True
    )
    repository = relationship('Repository')


class TestTaskArtifact(Base):

    __tablename__ = 'test_task_artifacts'
    id = sqlalchemy.Column(sqlalchemy.Integer, primary_key=True)
    test_task_id = sqlalchemy.Column(
        sqlalchemy.Integer,
        sqlalchemy.ForeignKey('test_tasks.id'),
        nullable=False
    )
    test_task = relationship('TestTask', back_populates='artifacts')
    name = sqlalchemy.Column(sqlalchemy.Text, nullable=False)
    href = sqlalchemy.Column(sqlalchemy.Text, nullable=False)


class Release(PermissionsMixin, Base):
    __tablename__ = 'build_releases'

    id = sqlalchemy.Column(sqlalchemy.Integer, primary_key=True)
    build_ids = sqlalchemy.Column(
        sqlalchemy.ARRAY(sqlalchemy.Integer, dimensions=1), nullable=False)
    build_task_ids = sqlalchemy.Column(
        sqlalchemy.ARRAY(sqlalchemy.Integer, dimensions=1), nullable=True)
    reference_platform_id = sqlalchemy.Column(
        sqlalchemy.Integer,
        nullable=True
    )
    platform_id = sqlalchemy.Column(
        sqlalchemy.Integer,
        sqlalchemy.ForeignKey('platforms.id'),
        nullable=False
    )
    platform = relationship('Platform')
    plan = sqlalchemy.Column(JSONB, nullable=True)
    status = sqlalchemy.Column(
        sqlalchemy.Integer,
        default=ReleaseStatus.SCHEDULED
    )


SignKeyRoleMapping = sqlalchemy.Table(
    'sign_key_role_mapping',
    Base.metadata,
    sqlalchemy.Column(
        'sign_key_id',
        sqlalchemy.Integer,
        sqlalchemy.ForeignKey('sign_keys.id'),
        primary_key=True
    ),
    sqlalchemy.Column(
        'role_id',
        sqlalchemy.Integer,
        sqlalchemy.ForeignKey('user_roles.id'),
        primary_key=True
    )
)


class SignKey(PermissionsMixin, Base):
    __tablename__ = 'sign_keys'

    id = sqlalchemy.Column(sqlalchemy.Integer, primary_key=True)
    name = sqlalchemy.Column(sqlalchemy.Text)
    description = sqlalchemy.Column(sqlalchemy.Text, nullable=True)
    keyid = sqlalchemy.Column(sqlalchemy.String(16), unique=True)
    fingerprint = sqlalchemy.Column(sqlalchemy.String(40), unique=True)
    public_url = sqlalchemy.Column(sqlalchemy.Text)
    inserted = sqlalchemy.Column(
        sqlalchemy.DateTime, default=datetime.datetime.utcnow())
    platform_id = sqlalchemy.Column(
        sqlalchemy.Integer,
        sqlalchemy.ForeignKey('platforms.id',
                              name='sign_keys_platform_id_fkey'),
        nullable=True)
    platform = relationship('Platform', back_populates='sign_keys')
    build_task_artifacts = relationship('BuildTaskArtifact',
                                        back_populates='sign_key')
    roles = relationship(
        'UserRole', secondary=SignKeyRoleMapping
    )


class SignTask(Base):
    __tablename__ = 'sign_tasks'

    id = sqlalchemy.Column(sqlalchemy.Integer, primary_key=True)
    build_id = sqlalchemy.Column(
        sqlalchemy.Integer,
        sqlalchemy.ForeignKey('builds.id'),
        nullable=False
    )
    build = relationship('Build')
    sign_key_id = sqlalchemy.Column(
        sqlalchemy.Integer,
        sqlalchemy.ForeignKey('sign_keys.id'),
        nullable=False
    )
    sign_key = relationship('SignKey')
    status = sqlalchemy.Column(
        sqlalchemy.Integer,
        default=SignStatus.IDLE
    )
    ts = sqlalchemy.Column(sqlalchemy.DateTime, nullable=True)
    error_message = sqlalchemy.Column(sqlalchemy.Text, nullable=True)
    log_href = sqlalchemy.Column(sqlalchemy.Text, nullable=True)


class ExportTask(Base):
    __tablename__ = 'export_tasks'

    id = sqlalchemy.Column(sqlalchemy.Integer, primary_key=True)
    name = sqlalchemy.Column(sqlalchemy.Text, nullable=False)
    status = sqlalchemy.Column(sqlalchemy.Integer, nullable=False)
    exported_at = sqlalchemy.Column(sqlalchemy.DateTime, nullable=True)


class RepoExporter(Base):
    __tablename__ = 'repo_exporters'

    id = sqlalchemy.Column(sqlalchemy.Integer, primary_key=True)
    path = sqlalchemy.Column(sqlalchemy.Text, nullable=False)
    exported_id = sqlalchemy.Column(
        sqlalchemy.Integer,
        sqlalchemy.ForeignKey('export_tasks.id'),
        nullable=False
    )
    repository_id = sqlalchemy.Column(
        sqlalchemy.Integer,
        sqlalchemy.ForeignKey('repositories.id'),
        nullable=False
    )
    repository = relationship('Repository')
    fs_exporter_href = sqlalchemy.Column(sqlalchemy.Text, nullable=False)


class PlatformFlavour(PermissionsMixin, Base):
    __tablename__ = 'platform_flavours'

    id = sqlalchemy.Column(sqlalchemy.Integer, primary_key=True)
    name = sqlalchemy.Column(sqlalchemy.Text, nullable=False, unique=True)
    modularity = sqlalchemy.Column(JSONB, nullable=True)
    repos = relationship('Repository', secondary=FlavourRepo)


# Errata/OVAL related tables 
class ErrataRecord(Base):
    __tablename__ = 'errata_records'

    id = sqlalchemy.Column(sqlalchemy.Text, primary_key=True)
    platform_id = sqlalchemy.Column(
        sqlalchemy.Integer,
        sqlalchemy.ForeignKey('platforms.id'),
        nullable=False
    )
    platform = relationship('Platform')
    summary = sqlalchemy.Column(sqlalchemy.Text, nullable=True)
    solution = sqlalchemy.Column(sqlalchemy.Text, nullable=True)

    freezed = sqlalchemy.Column(sqlalchemy.Boolean, nullable=True)

    issued_date = sqlalchemy.Column(sqlalchemy.DateTime, nullable=False)
    updated_date = sqlalchemy.Column(sqlalchemy.DateTime, nullable=False)
    description = sqlalchemy.Column(sqlalchemy.Text, nullable=True)
    original_description = sqlalchemy.Column(sqlalchemy.Text, nullable=False)
    title = sqlalchemy.Column(sqlalchemy.Text, nullable=True)
    original_title = sqlalchemy.Column(sqlalchemy.Text, nullable=False)
    contact_mail = sqlalchemy.Column(sqlalchemy.Text, nullable=False)
    status = sqlalchemy.Column(sqlalchemy.Text, nullable=False)
    version = sqlalchemy.Column(sqlalchemy.Text, nullable=False)
    severity = sqlalchemy.Column(sqlalchemy.Text, nullable=False)
    rights = sqlalchemy.Column(sqlalchemy.Text, nullable=False)
    # OVAL-only fields
    definition_id = sqlalchemy.Column(sqlalchemy.Text, nullable=False)
    definition_version = sqlalchemy.Column(sqlalchemy.Text, nullable=False)
    definition_class = sqlalchemy.Column(sqlalchemy.Text, nullable=False)
    affected_cpe = sqlalchemy.Column(JSONB, nullable=False, default=[])
    criteria = sqlalchemy.Column(JSONB, nullable=True)
    original_criteria = sqlalchemy.Column(JSONB, nullable=True)
    tests = sqlalchemy.Column(JSONB, nullable=True)
    original_tests = sqlalchemy.Column(JSONB, nullable=True)
    objects = sqlalchemy.Column(JSONB, nullable=True)
    original_objects = sqlalchemy.Column(JSONB, nullable=True)
    states = sqlalchemy.Column(JSONB, nullable=True)
    original_states = sqlalchemy.Column(JSONB, nullable=True)
    variables = sqlalchemy.Column(JSONB, nullable=True)
    original_variables = sqlalchemy.Column(JSONB, nullable=True)

    references = relationship('ErrataReference')
    packages = relationship('ErrataPackage')

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
        #              ALEA -> (EA) -> enchancement
        return {
            'BA': 'bugfix',
            'SA': 'security',
            'EA': 'enhancement',
        }[self.id[2:4]]


class ErrataReferenceType(enum.Enum):
    cve = 'cve'
    rhsa = 'rhsa'
    self_ref = 'self'
    bugzilla = 'bugzilla'


class ErrataReference(Base):
    __tablename__ = 'errata_references'

    id = sqlalchemy.Column(sqlalchemy.Integer, primary_key=True)
    href = sqlalchemy.Column(sqlalchemy.Text, nullable=False)
    ref_id = sqlalchemy.Column(sqlalchemy.Text, nullable=False)
    title = sqlalchemy.Column(sqlalchemy.Text, nullable=False)
    ref_type = sqlalchemy.Column(sqlalchemy.Enum(ErrataReferenceType), nullable=False)
    errata_record_id = sqlalchemy.Column(
        sqlalchemy.Text,
        sqlalchemy.ForeignKey('errata_records.id'),
        nullable=False
    )
    cve = relationship('ErrataCVE')
    cve_id = sqlalchemy.Column(
        sqlalchemy.Text,
        sqlalchemy.ForeignKey('errata_cves.id'),
        nullable=True
    )


class ErrataCVE(Base):
    __tablename__ = 'errata_cves'

    id = sqlalchemy.Column(sqlalchemy.Text, primary_key=True)
    cvss3 = sqlalchemy.Column(sqlalchemy.Text, nullable=False)
    cwe = sqlalchemy.Column(sqlalchemy.Text, nullable=True)
    impact = sqlalchemy.Column(sqlalchemy.Text, nullable=True)
    public = sqlalchemy.Column(sqlalchemy.Text, nullable=False)


class ErrataPackage(Base):
    __tablename__ = 'errata_packages'

    id = sqlalchemy.Column(sqlalchemy.Integer, primary_key=True)
    errata_record_id = sqlalchemy.Column(
        sqlalchemy.Text,
        sqlalchemy.ForeignKey('errata_records.id'),
        nullable=False
    )
    name = sqlalchemy.Column(sqlalchemy.Text, nullable=False)
    version = sqlalchemy.Column(sqlalchemy.Text, nullable=False)
    release = sqlalchemy.Column(sqlalchemy.Text, nullable=False)
    epoch = sqlalchemy.Column(sqlalchemy.Integer, nullable=False)
    arch = sqlalchemy.Column(sqlalchemy.Text, nullable=False)
    source_srpm = sqlalchemy.Column(sqlalchemy.Text, nullable=True)
    reboot_suggested = sqlalchemy.Column(sqlalchemy.Boolean, nullable=False)
    albs_packages = relationship('ErrataToALBSPackage', back_populates='errata_package')


class ErrataPackageStatus(enum.Enum):
    proposal = 'proposal'
    skipped = 'skipped'
    released = 'released'
    approved = 'approved'


class ErrataToALBSPackage(Base):
    __tablename__ = 'errata_to_albs_packages'
    __table_args___ = (
        sqlalchemy.CheckConstraint(
            'albs_artifact_id IS NOT NULL '
            'OR '
            'pulp_href IS NOT NULL',
            name='errata_to_albs_package_integrity_check'
        ),
    )
    
    id = sqlalchemy.Column(sqlalchemy.Integer, primary_key=True)
    errata_package_id = sqlalchemy.Column(
        sqlalchemy.Integer,
        sqlalchemy.ForeignKey('errata_packages.id'),
        nullable=False
    )
    errata_package = relationship('ErrataPackage', back_populates='albs_packages')
    albs_artifact_id = sqlalchemy.Column(
        sqlalchemy.Integer,
        sqlalchemy.ForeignKey('build_artifacts.id'),
        nullable=True
    )
    build_artifact = relationship('BuildTaskArtifact')
    pulp_href = sqlalchemy.Column(sqlalchemy.Text, nullable=True)
    status = sqlalchemy.Column(sqlalchemy.Enum(ErrataPackageStatus), nullable=False)

    name = sqlalchemy.Column(sqlalchemy.Text, nullable=False)
    arch = sqlalchemy.Column(sqlalchemy.Text, nullable=False)
    version = sqlalchemy.Column(sqlalchemy.Text, nullable=False)
    release = sqlalchemy.Column(sqlalchemy.Text, nullable=False)
    epoch = sqlalchemy.Column(sqlalchemy.Integer, nullable=False)

    @property
    def build_id(self):
        if self.build_artifact:
            return self.build_artifact.build_task.build_id
    
    @property
    def task_id(self):
        if self.build_artifact:
            return self.build_artifact.build_task.id
    

async def create_tables():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


if __name__ == '__main__':
    asyncio.run(create_tables())

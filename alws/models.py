import asyncio
import datetime

import sqlalchemy
from sqlalchemy.orm import relationship
from sqlalchemy.dialects.postgresql import JSONB

from alws.constants import ReleaseStatus, SignStatus
from alws.database import Base, engine


__all__ = ['Platform', 'Build', 'BuildTask', 'Distribution']


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


class Platform(Base):

    __tablename__ = 'platforms'

    id = sqlalchemy.Column(sqlalchemy.Integer, primary_key=True)
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
    arch_list = sqlalchemy.Column(JSONB, nullable=False)
    data = sqlalchemy.Column(JSONB, nullable=False)
    repos = relationship('Repository', secondary=PlatformRepo)


class Distribution(Base):

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


class Repository(CustomRepoRepr):

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


class RepositoryRemote(CustomRepoRepr):
    __tablename__ = 'repository_remotes'
    __tableargs__ = [
        sqlalchemy.UniqueConstraint('name', 'arch', 'url')
    ]

    id = sqlalchemy.Column(sqlalchemy.Integer, primary_key=True)
    name = sqlalchemy.Column(sqlalchemy.Text, nullable=False)
    arch = sqlalchemy.Column(sqlalchemy.Text, nullable=False)
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


class Build(Base):

    __tablename__ = 'builds'

    id = sqlalchemy.Column(sqlalchemy.Integer, primary_key=True)
    user_id = sqlalchemy.Column(
        sqlalchemy.Integer,
        sqlalchemy.ForeignKey('users.id'),
        nullable=False
    )
    created_at = sqlalchemy.Column(
        sqlalchemy.DateTime,
        nullable=False,
        # TODO: replace with sql function
        default=datetime.datetime.utcnow
    )
    tasks = relationship('BuildTask', back_populates='build')
    repos = relationship('Repository', secondary=BuildRepo)
    user = relationship('User')
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
    mock_options = sqlalchemy.Column(JSONB)
    ref = relationship('BuildTaskRef')
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
    builted_srpm_url = sqlalchemy.Column(sqlalchemy.VARCHAR, nullable=True)


class BuildTaskRef(Base):

    __tablename__ = 'build_task_refs'

    id = sqlalchemy.Column(sqlalchemy.Integer, primary_key=True)
    url = sqlalchemy.Column(sqlalchemy.TEXT, nullable=False)
    git_ref = sqlalchemy.Column(sqlalchemy.TEXT)
    ref_type = sqlalchemy.Column(sqlalchemy.Integer)


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


class User(Base):

    __tablename__ = 'users'

    id = sqlalchemy.Column(sqlalchemy.Integer, primary_key=True)
    username = sqlalchemy.Column(sqlalchemy.TEXT, nullable=False)
    email = sqlalchemy.Column(sqlalchemy.TEXT, nullable=False)
    jwt_token = sqlalchemy.Column(sqlalchemy.TEXT)
    github_token = sqlalchemy.Column(sqlalchemy.TEXT)


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


class Release(Base):
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
    created_by_id = sqlalchemy.Column(
        sqlalchemy.Integer,
        sqlalchemy.ForeignKey('users.id'),
        nullable=False
    )
    status = sqlalchemy.Column(
        sqlalchemy.Integer,
        default=ReleaseStatus.SCHEDULED
    )
    created_by = relationship('User')


class SignKey(Base):
    __tablename__ = 'sign_keys'

    id = sqlalchemy.Column(sqlalchemy.Integer, primary_key=True)
    name = sqlalchemy.Column(sqlalchemy.Text)
    description = sqlalchemy.Column(sqlalchemy.Text, nullable=True)
    keyid = sqlalchemy.Column(sqlalchemy.String(16), unique=True)
    fingerprint = sqlalchemy.Column(sqlalchemy.String(40), unique=True)
    public_url = sqlalchemy.Column(sqlalchemy.Text)
    inserted = sqlalchemy.Column(
        sqlalchemy.DateTime, default=datetime.datetime.utcnow())


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


async def create_tables():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


if __name__ == '__main__':
    asyncio.run(create_tables())

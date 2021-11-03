import asyncio
import datetime

import sqlalchemy
from sqlalchemy.orm import relationship
from sqlalchemy.dialects.postgresql import JSONB

from alws.constants import ReleaseStatus
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


class Repository(Base):

    __tablename__ = 'repositories'

    id = sqlalchemy.Column(sqlalchemy.Integer, primary_key=True)
    name = sqlalchemy.Column(sqlalchemy.Text, nullable=False)
    arch = sqlalchemy.Column(sqlalchemy.Text, nullable=False)
    url = sqlalchemy.Column(sqlalchemy.Text, nullable=False)
    type = sqlalchemy.Column(sqlalchemy.Text, nullable=False)
    debug = sqlalchemy.Column(sqlalchemy.Boolean, default=False)
    production = sqlalchemy.Column(sqlalchemy.Boolean, default=False,
                                   nullable=True)
    pulp_href = sqlalchemy.Column(sqlalchemy.Text)


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
    status = sqlalchemy.Column(sqlalchemy.Integer, nullable=False)
    index = sqlalchemy.Column(sqlalchemy.Integer, nullable=False)
    arch = sqlalchemy.Column(sqlalchemy.VARCHAR(length=50), nullable=False)
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


class BuildTaskRef(Base):

    __tablename__ = 'build_task_refs'

    id = sqlalchemy.Column(sqlalchemy.Integer, primary_key=True)
    # TODO: think if type can be integer
    url = sqlalchemy.Column(sqlalchemy.TEXT, nullable=False)
    git_ref = sqlalchemy.Column(sqlalchemy.TEXT)


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


async def create_tables():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


if __name__ == '__main__':
    asyncio.run(create_tables())

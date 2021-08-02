import asyncio
import datetime

import sqlalchemy
from sqlalchemy.orm import relationship
from sqlalchemy.dialects.postgresql import JSONB

from alws.database import Base, engine


__all__ = ['Platform', 'Build', 'BuildTask']


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


class Platform(Base):

    __tablename__ = 'platforms'

    id = sqlalchemy.Column(sqlalchemy.Integer, primary_key=True)
    type = sqlalchemy.Column(sqlalchemy.Text, nullable=False)
    distr_type = sqlalchemy.Column(sqlalchemy.Text, nullable=False)
    distr_version = sqlalchemy.Column(sqlalchemy.Text, nullable=False)
    name = sqlalchemy.Column(
        sqlalchemy.Text,
        nullable=False,
        unique=True,
        index=True
    )
    arch_list = sqlalchemy.Column(JSONB, nullable=False)
    data = sqlalchemy.Column(JSONB, nullable=False)
    repos = relationship('Repository', secondary=PlatformRepo)


class Repository(Base):

    __tablename__ = 'repositories'

    id = sqlalchemy.Column(sqlalchemy.Integer, primary_key=True)
    name = sqlalchemy.Column(sqlalchemy.Text, nullable=False)
    arch = sqlalchemy.Column(sqlalchemy.Text, nullable=False)
    url = sqlalchemy.Column(sqlalchemy.Text, nullable=False)
    type = sqlalchemy.Column(sqlalchemy.Text, nullable=False)
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
    platform = relationship('Platform')
    build = relationship('Build', back_populates='tasks')
    dependencies = relationship(
        'BuildTask',
        secondary=BuildTaskDependency,
        primaryjoin=(BuildTaskDependency.c.build_task_id == id),
        secondaryjoin=(BuildTaskDependency.c.build_task_dependency == id)
    )
    ref = relationship('BuildTaskRef')


class BuildTaskRef(Base):

    __tablename__ = 'build_task_refs'

    id = sqlalchemy.Column(sqlalchemy.Integer, primary_key=True)
    # TODO: think if type can be integer
    ref_type = sqlalchemy.Column(sqlalchemy.TEXT, nullable=False)
    url = sqlalchemy.Column(sqlalchemy.TEXT, nullable=False)
    git_ref = sqlalchemy.Column(sqlalchemy.TEXT)


class User(Base):

    __tablename__ = 'users'

    id = sqlalchemy.Column(sqlalchemy.Integer, primary_key=True)
    username = sqlalchemy.Column(sqlalchemy.TEXT, nullable=False)
    email = sqlalchemy.Column(sqlalchemy.TEXT, nullable=False)
    jwt_token = sqlalchemy.Column(sqlalchemy.TEXT)
    github_token = sqlalchemy.Column(sqlalchemy.TEXT)


async def create_tables():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


if __name__ == '__main__':
    asyncio.run(create_tables())

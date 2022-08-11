# -*- mode:python; coding:utf-8; -*-
# author: Vyacheslav Potoropin <vpotoropin@almalinux.org>
# created: 2021-06-22
from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.orm import scoped_session, sessionmaker

from alws.config import settings


__all__ = [
    'engine',
    'PulpBase',
    'PulpSession',
    'pulp_engine',
]

engine = create_async_engine(settings.async_sqlalchemy_url)

PulpBase = declarative_base()
pulp_engine = create_engine(settings.pulp_database_url,
                            pool_pre_ping=True, pool_recycle=3600)
pulp_session_factory = sessionmaker(pulp_engine, expire_on_commit=False)
PulpSession = scoped_session(pulp_session_factory)

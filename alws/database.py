# -*- mode:python; coding:utf-8; -*-
# author: Vyacheslav Potoropin <vpotoropin@almalinux.org>
# created: 2021-06-22
from typing import AsyncGenerator

from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import scoped_session, sessionmaker
from sqlalchemy.pool import NullPool

from alws.config import settings


__all__ = ['Base', 'Session', 'engine']


DATABASE_URL = settings.database_url

engine = create_async_engine(DATABASE_URL, poolclass=NullPool)
sync_engine = create_engine(settings.sync_database_url,
                            pool_pre_ping=True, pool_recycle=3600)
Base = declarative_base()
sync_session_factory = sessionmaker(sync_engine, expire_on_commit=False)
Session = sessionmaker(
    engine, expire_on_commit=False, class_=AsyncSession
)
SyncSession = scoped_session(sync_session_factory)


async def get_async_session() -> AsyncGenerator[AsyncSession, None]:
    async with Session() as session:
        yield session

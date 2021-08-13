# -*- mode:python; coding:utf-8; -*-
# author: Vyacheslav Potoropin <vpotoropin@almalinux.org>
# created: 2021-06-22

from alws.config import settings

from sqlalchemy.orm import sessionmaker
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine


__all__ = ['Base', 'Session']


DATABASE_URL = settings.database_url

engine = create_async_engine(DATABASE_URL)
Base = declarative_base()
Session = sessionmaker(
    engine, expire_on_commit=False, class_=AsyncSession
)

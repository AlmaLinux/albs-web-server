# -*- mode:python; coding:utf-8; -*-
# author: Vyacheslav Potoropin <vpotoropin@almalinux.org>
# created: 2021-06-22
from sqlalchemy import MetaData
from sqlalchemy.ext.asyncio import AsyncAttrs
from sqlalchemy.orm import DeclarativeBase

__all__ = ['Base', 'PulpBase']


class Base(AsyncAttrs, DeclarativeBase):
    __allow_unmapped__ = True
    metadata = MetaData()


# Pulp db
class PulpBase(AsyncAttrs, DeclarativeBase):
    __allow_unmapped__ = True

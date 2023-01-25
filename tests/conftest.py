from contextlib import asynccontextmanager
import datetime
import uuid

import pytest
from sqlalchemy import insert, select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.pool import NullPool
import yaml

from alws import models
from alws.config import settings
from alws.database import Base
from alws.schemas import (
    repository_schema,
    platform_schema,
)
from alws.utils.pulp_client import PulpClient
from tests.constants import ADMIN_USER_ID


engine = create_async_engine(
    settings.test_database_url,
    poolclass=NullPool,
    echo_pool=True,
)


async def get_session():
    async with AsyncSession(engine) as sess:
        try:
            yield sess
        finally:
            await sess.close()


@pytest.fixture(scope="session")
def anyio_backend():
    return "asyncio"


@pytest.mark.anyio
@pytest.fixture(scope="module", autouse=True)
async def create_tables():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


@pytest.mark.anyio
@pytest.fixture
async def session():
    async with asynccontextmanager(get_session)() as session:
        yield session


@pytest.mark.anyio
@pytest.fixture(
    autouse=True,
    params=[
        {
            "id": ADMIN_USER_ID,
            "username": "admin",
            "email": "admin@almalinux.com",
            "is_superuser": True,
            "is_verified": True,
        },
    ],
)
async def create_user(session, request):
    data = {
        "id": request.param["id"],
        "username": request.param["username"],
        "email": request.param["email"],
        "is_superuser": request.param["is_superuser"],
        "is_verified": request.param["is_verified"],
    }
    user = await (
        session.execute(
            select(models.User).where(models.User.id == data["id"]),
        )
    )
    if user.scalars().first():
        return
    await session.execute(insert(models.User).values(**data))
    await session.commit()


@pytest.fixture(
    params=[
        ADMIN_USER_ID,
    ]
)
def product_create_payload(request):
    return {
        "name": "AlmaLinux",
        "owner_id": request.param,
        "title": "AlmaLinux",
        "description": "",
        "platforms": [
            {
                "id": 1,
                "name": "AlmaLinux-8",
                "distr_type": "rhel",
                "distr_version": "8",
                "arch_list": [
                    "i686",
                    "x86_64",
                    "ppc64le",
                    "aarch64",
                    "s390x",
                ],
                "modularity": {},
            },
        ],
        "is_community": True,
    }


@pytest.fixture(
    params=[
        {
            "id": "ALSA-2022:0123",
        },
    ]
)
def errata_create_payload(request):
    orig_id = request.param["id"].replace("ALSA", "RHSA")
    return {
        "id": request.param["id"],
        "freezed": False,
        "platform_id": 1,
        "issued_date": str(datetime.date(2022, 10, 22)),
        "updated_date": str(datetime.date(2022, 10, 22)),
        "title": "",
        "description": "",
        "status": "final",
        "version": "1",
        "severity": "Moderate",
        "rights": "Copyright 2023 AlmaLinux OS",
        "definition_id": "oval:com.redhat.rhsa:def:20230087",
        "definition_version": "635",
        "definition_class": "patch",
        "affected_cpe": [
            "cpe:/a:redhat:enterprise_linux:8",
            "cpe:/a:redhat:enterprise_linux:8::appstream",
        ],
        "criteria": None,
        "tests": None,
        "objects": None,
        "states": None,
        "variables": None,
        "references": [
            {
                "href": f"https://access.redhat.com/errata/{orig_id}",
                "ref_id": orig_id,
                "ref_type": "rhsa",
                "title": orig_id,
                "cve": {
                    "id": "CVE-2022-21618",
                    "cvss3": "CVSS:3.1/AV:N/AC:L/PR:N/UI:N/S:U/C:N/I:L/A:N",
                    "cwe": "CWE-120",
                    "impact": "Moderate",
                    "public": "2022-10-18T20:00:00Z",
                },
            }
        ],
        "packages": [
            {
                "name": "usbguard",
                "version": "1.0.0",
                "release": "8.el8_7.2",
                "epoch": 0,
                "arch": "x86_64",
                "reboot_suggested": False,
            }
        ],
    }


@pytest.mark.anyio
@pytest.fixture
async def create_base_platform(session):
    with open("reference_data/platforms.yaml", "rt") as file:
        loader = yaml.Loader(file)
        platform_data = loader.get_data()[0]
    schema = platform_schema.PlatformCreate(**platform_data).dict()
    schema["repos"] = []
    platform = models.Platform(**schema)
    for repo in platform_data.get("repositories", []):
        repo["url"] = repo["remote_url"]
        repo["pulp_href"] = f"/pulp/api/v3/repositories/rpm/rpm/{uuid.uuid1()}/"
        repository = models.Repository(
            **repository_schema.RepositoryCreate(**repo).dict()
        )
        platform.repos.append(repository)
    session.add(platform)
    await session.commit()


@pytest.fixture(autouse=True)
def mock_create_repo(monkeypatch):
    async def func():
        repo_url = "mock_url"
        repo_href = "mock_href"
        return repo_url, repo_href

    monkeypatch.setattr(PulpClient, "create_rpm_repository", func)


@pytest.fixture(autouse=True)
def mock_get_packages_from_pulp_repo(monkeypatch):
    def func(*args, **kwargs):
        return []

    monkeypatch.setattr("alws.crud.errata.get_rpm_packages_from_repository", func)


@pytest.fixture(autouse=True)
def mock_get_packages_from_pulp_by_ids(monkeypatch):
    def func(*args, **kwargs):
        return {}

    monkeypatch.setattr("alws.crud.errata.get_rpm_packages_by_ids", func)

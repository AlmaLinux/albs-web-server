import asyncio

import pytest

pytest_plugins = [
    "tests.fixtures.builds",
    "tests.fixtures.database",
    "tests.fixtures.dramatiq",
    "tests.fixtures.errata",
    "tests.fixtures.modularity",
    "tests.fixtures.platforms",
    "tests.fixtures.products",
    "tests.fixtures.pulp",
]


@pytest.fixture(scope="session")
def event_loop():
    return asyncio.get_event_loop()


@pytest.fixture(scope="session")
def alembic_ini_path():
    return './alws/alembic.ini'


@pytest.fixture(scope="session")
def db_migration(db_migration):
    pass


@pytest.fixture(scope="session")
def anyio_backend():
    return "asyncio"


@pytest.fixture
def sqla_modules():
    from alws import models


@pytest.fixture(scope="session")
def db_url():
    return 'postgresql+psycopg2://postgres:password@db/test-almalinux-bs'


@pytest.fixture(scope="session")
def async_sqlalchemy_url():
    return 'postgresql+asyncpg://postgres:password@db/test-almalinux-bs'


@pytest.fixture(scope="session")
def db(async_session):
    pass

import pytest

pytest_plugins = [
    "tests.fixtures.beholder",
    "tests.fixtures.builds",
    "tests.fixtures.database",
    "tests.fixtures.dramatiq",
    "tests.fixtures.errata",
    "tests.fixtures.modularity",
    "tests.fixtures.platforms",
    "tests.fixtures.products",
    "tests.fixtures.pulp",
    "tests.fixtures.releases",
    "tests.fixtures.repositories",
]


@pytest.fixture(scope="session")
def anyio_backend():
    return "asyncio"

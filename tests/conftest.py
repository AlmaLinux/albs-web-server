import pytest

pytest_plugins = [
    "tests.fixtures.beholder",
    "tests.fixtures.builds",
    "tests.fixtures.database",
    "tests.fixtures.dramatiq",
    "tests.fixtures.errata",
    "tests.fixtures.limiter",
    "tests.fixtures.modularity",
    "tests.fixtures.package_info",
    "tests.fixtures.platforms",
    "tests.fixtures.products",
    "tests.fixtures.pulp",
    "tests.fixtures.releases",
    "tests.fixtures.repositories",
    "tests.fixtures.sign_keys",
    "tests.fixtures.tests",
    "tests.fixtures.uploader",
]


@pytest.fixture(scope="session")
def anyio_backend():
    return "asyncio"

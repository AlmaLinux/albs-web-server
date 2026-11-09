import uuid

import pytest
from fastapi_sqla import open_async_session
from sqlalchemy import text

from alws.utils.pulp_utils import get_rpm_package_hrefs

pytestmark = pytest.mark.anyio

PACKAGES = (
    ("bash", "0", "5.1.8", "9.el9", "x86_64"),
    ("bash", "0", "5.1.8", "9.el9", "aarch64"),
    ("bash", "0", "5.1.8", "6.el9", "x86_64"),
    ("bash-doc", "0", "5.1.8", "9.el9", "noarch"),
    ("kernel", "0", "5.14.0", "570.el9", "x86_64"),
)


@pytest.fixture
async def rpm_packages():
    """
    The test database has no Pulp schema, so create the columns of
    rpm_package that the lookup uses.
    """
    ids = {}
    async with open_async_session(key="pulp_async") as pulp_db:
        await pulp_db.execute(
            text(
                "CREATE TABLE rpm_package (content_ptr_id uuid PRIMARY KEY, "
                "name varchar(255), epoch varchar(10), version varchar(255), "
                "release varchar(255), arch varchar(20))"
            )
        )
        for package in PACKAGES:
            package_id = uuid.uuid4()
            ids[package] = package_id
            await pulp_db.execute(
                text(
                    "INSERT INTO rpm_package VALUES "
                    "(:id, :name, :epoch, :version, :release, :arch)"
                ),
                dict(
                    zip(
                        ("id", "name", "epoch", "version", "release", "arch"),
                        (package_id, *package),
                    )
                ),
            )
    yield ids
    async with open_async_session(key="pulp_async") as pulp_db:
        await pulp_db.execute(text("DROP TABLE rpm_package"))


def hrefs_of(ids, *packages):
    return sorted(
        f"/pulp/api/v3/content/rpm/packages/{ids[package]}/"
        for package in packages
    )


@pytest.mark.parametrize(
    "params, expected",
    [
        # exact name, not a prefix: bash-doc isn't found
        ({"name": "bash"}, PACKAGES[:3]),
        ({"name": "bash", "release": "9.el9"}, PACKAGES[:2]),
        ({"name": "bash", "arch": "x86_64"}, (PACKAGES[0], PACKAGES[2])),
        (
            {
                "name": "bash",
                "epoch": "0",
                "version": "5.1.8",
                "release": "9.el9",
                "arch": "aarch64",
            },
            (PACKAGES[1],),
        ),
        # empty values don't filter, as in the Pulp API
        ({"name": "kernel", "arch": ""}, (PACKAGES[4],)),
        ({"name": "nosuchpackage"}, ()),
    ],
)
async def test_get_rpm_package_hrefs(rpm_packages, params, expected):
    async with open_async_session(key="pulp_async") as pulp_db:
        hrefs = await get_rpm_package_hrefs(pulp_db, **params)

    assert sorted(hrefs) == hrefs_of(rpm_packages, *expected)

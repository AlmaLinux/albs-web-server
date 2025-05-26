import datetime
from typing import Any, Dict, List

import pytest

from alws.errors import PlatformNotFoundError, RepositoriesNotFoundError


@pytest.fixture
def package_info() -> List[Dict[str, Any]]:
    return [
        {
            "name": "example_package",
            "version": "1.0",
            "release": "1.el8",
            "changelogs": ["Initial release"],
        },
        {
            "name": "example_package",
            "version": "1.1",
            "release": "2.el9",
            "changelogs": ["Bug fixes"],
        },
    ]


@pytest.fixture
def mock_get_package_info_success(monkeypatch, package_info):
    async def mock_func(*args, **kwargs):
        return package_info

    monkeypatch.setattr("alws.crud.package_info.get_package_info", mock_func)


@pytest.fixture
def mock_get_package_info_platform_not_found(monkeypatch):
    async def mock_func(*args, **kwargs):
        raise PlatformNotFoundError("Invalid distribution: AlmaLinux-999")

    monkeypatch.setattr("alws.crud.package_info.get_package_info", mock_func)


@pytest.fixture
def mock_get_package_info_repos_not_found(monkeypatch):
    async def mock_func(*args, **kwargs):
        raise RepositoriesNotFoundError("No repositories found")

    monkeypatch.setattr("alws.crud.package_info.get_package_info", mock_func)


@pytest.fixture
def mock_get_package_info_empty(monkeypatch):
    async def mock_func(*args, **kwargs):
        return []

    monkeypatch.setattr("alws.crud.package_info.get_package_info", mock_func)


@pytest.fixture
def mock_get_package_info_with_date_filter(monkeypatch):
    async def mock_func(*args, **kwargs):
        updated_after = args[-1]
        packages = [
            {
                "name": "example_package",
                "version": "1.0",
                "release": "1.el8",
                "changelogs": ["Initial release"],
                "pulp_last_updated": "2024-01-01 10:00:00",
            },
            {
                "name": "example_package",
                "version": "1.1",
                "release": "2.el9",
                "changelogs": ["Security patch"],
                "pulp_last_updated": "2024-06-01 12:00:00",
            },
        ]

        if updated_after:
            cutoff = datetime.datetime.strptime(
                updated_after, "%Y-%m-%d %H:%M:%S"
            )
            filtered = [
                {k: v for k, v in pkg.items() if k != "pulp_last_updated"}
                for pkg in packages
                if datetime.datetime.strptime(
                    pkg["pulp_last_updated"], "%Y-%m-%d %H:%M:%S"
                )
                >= cutoff
            ]
        else:
            filtered = [
                {k: v for k, v in pkg.items() if k != "pulp_last_updated"}
                for pkg in packages
            ]

        return filtered

    monkeypatch.setattr("alws.crud.package_info.get_package_info", mock_func)

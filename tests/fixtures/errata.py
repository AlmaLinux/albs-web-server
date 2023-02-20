import datetime

import pytest


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

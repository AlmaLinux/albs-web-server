from types import SimpleNamespace

from alws.constants import ErrataPackageStatus
from alws.crud.errata import (
    get_albs_packages_from_record,
    prepare_search_params,
)

ERRATA_RELEASE = "3.module_el9.1.0+10+aaaa1111.1.alma.1"
OTHER_CONTEXT_RELEASE = "3.module_el9.1.0+8+bbbb2222.1"
REBUILD_RELEASE = "3.module_el9.1.0+12+cccc3333.1.alma.2"
REPO = "/pulp/api/v3/repositories/rpm/rpm/repo/"


def make_albs_package(href, release, status=ErrataPackageStatus.released):
    return SimpleNamespace(
        name="foo",
        version="1.0.0",
        release=release,
        epoch=2,
        arch="x86_64",
        status=status,
        get_pulp_href=lambda: href,
    )


def make_record(record_id, albs_packages):
    package = SimpleNamespace(
        name="foo",
        version="1.0.0",
        release=ERRATA_RELEASE,
        epoch=2,
        arch="x86_64",
        albs_packages=albs_packages,
    )
    for albs_package in albs_packages:
        albs_package.errata_package = package
    return SimpleNamespace(
        id=record_id,
        is_issued_by_almalinux=record_id.startswith("ALSA-2099:A"),
        packages=[package],
    )


def test_search_params_include_mapped_releases():
    record = make_record(
        "ALSA-2099:A001",
        [
            make_albs_package("/a/", OTHER_CONTEXT_RELEASE),
            make_albs_package("/b/", REBUILD_RELEASE),
            make_albs_package(
                "/c/",
                "4.el9",
                status=ErrataPackageStatus.skipped,
            ),
        ],
    )

    params = prepare_search_params(record, include_albs_releases=True)

    assert params["release"] == [
        ERRATA_RELEASE,
        OTHER_CONTEXT_RELEASE,
        REBUILD_RELEASE,
    ]


def test_search_params_default_keeps_errata_release_only():
    record = make_record(
        "ALSA-2099:A001",
        [make_albs_package("/a/", OTHER_CONTEXT_RELEASE)],
    )

    params = prepare_search_params(record)

    assert params["release"] == [ERRATA_RELEASE]


def test_search_params_no_release_for_upstream_records():
    record = make_record(
        "ALSA-2099:0001",
        [make_albs_package("/a/", OTHER_CONTEXT_RELEASE)],
    )

    params = prepare_search_params(record, include_albs_releases=True)

    assert "release" not in params


def test_record_with_other_context_mapping_is_releasable():
    albs_package = make_albs_package("/a/", OTHER_CONTEXT_RELEASE)
    record = make_record("ALSA-2099:A001", [albs_package])

    repo_mapping, missing = get_albs_packages_from_record(
        record,
        {"/a/": [REPO]},
    )

    assert missing == []
    assert repo_mapping == {REPO: [albs_package]}

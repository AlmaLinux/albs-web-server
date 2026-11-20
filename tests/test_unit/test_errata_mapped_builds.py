import itertools
from types import SimpleNamespace

import pytest

from alws.constants import ErrataPackageStatus, ErrataPackagesType
from alws.crud.errata import (
    get_albs_packages_from_record,
    get_matching_albs_packages,
    prepare_search_params,
    select_prod_package,
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


def make_prod_package(release, epoch="2", sourcerpm=True):
    return SimpleNamespace(
        name="foo",
        version="1.0.0",
        release=release,
        epoch=epoch,
        arch="x86_64",
        pulp_href=f"/pulp/api/v3/content/rpm/packages/{release}/",
        rpm_sourcerpm=f"foo-1.0.0-{release}.src.rpm" if sourcerpm else "",
    )


def make_errata_package(release=ERRATA_RELEASE):
    return SimpleNamespace(
        name="foo",
        version="1.0.0",
        release=release,
        epoch=2,
        arch="x86_64",
        source_srpm=None,
        albs_packages=[],
    )


@pytest.mark.parametrize(
    "candidates",
    [
        pytest.param(list(order), id="-".join(str(i) for i in indices))
        for indices, order in zip(
            itertools.permutations(range(3)),
            itertools.permutations([
                make_prod_package(OTHER_CONTEXT_RELEASE),
                make_prod_package(ERRATA_RELEASE),
                make_prod_package(REBUILD_RELEASE),
            ]),
        )
    ],
)
def test_select_prefers_exact_release_in_any_order(candidates):
    selected = select_prod_package(make_errata_package(), candidates)

    assert selected.release == ERRATA_RELEASE


@pytest.mark.parametrize(
    "candidates",
    [
        pytest.param(list(order), id="-".join(str(i) for i in indices))
        for indices, order in zip(
            itertools.permutations(range(3)),
            itertools.permutations([
                make_prod_package("3.module_el9.1.0+8+bbbb2222.1"),
                make_prod_package("3.module_el9.1.0+12+cccc3333.1.alma.2"),
                make_prod_package("3.module_el9.1.0+12+cccc3333.1.alma.1"),
            ]),
        )
    ],
)
def test_select_falls_back_to_highest_evr(candidates):
    errata_package = make_errata_package("3.module_el9.1.0+5+dddd4444.1")

    selected = select_prod_package(errata_package, candidates)

    assert selected.release == "3.module_el9.1.0+12+cccc3333.1.alma.2"


def test_select_skips_packages_without_sourcerpm():
    candidates = [
        make_prod_package(ERRATA_RELEASE, sourcerpm=False),
        make_prod_package(OTHER_CONTEXT_RELEASE),
    ]

    selected = select_prod_package(make_errata_package(), candidates)

    assert selected.release == OTHER_CONTEXT_RELEASE


def test_select_returns_none_without_usable_candidates():
    candidates = [make_prod_package(ERRATA_RELEASE, sourcerpm=False)]

    assert select_prod_package(make_errata_package(), candidates) is None


@pytest.mark.anyio
async def test_matching_maps_one_deterministic_prod_build():
    errata_package = make_errata_package()
    prod_repos_cache = {
        "foo-1.0.0-3.1": {
            "x86_64": [
                make_prod_package(REBUILD_RELEASE),
                make_prod_package(OTHER_CONTEXT_RELEASE),
                make_prod_package(ERRATA_RELEASE),
            ],
        },
    }

    items, package_type = await get_matching_albs_packages(
        None,
        errata_package,
        prod_repos_cache,
    )

    assert package_type == {"type": ErrataPackagesType.PROD}
    assert [item.release for item in items] == [ERRATA_RELEASE]
    assert items[0].status == ErrataPackageStatus.released
    assert errata_package.albs_packages == items
    assert errata_package.source_srpm == "foo"

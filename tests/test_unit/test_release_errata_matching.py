import itertools
from types import SimpleNamespace

from alws.constants import ErrataPackageStatus
from alws.release_planner import AlmaLinuxReleasePlanner
from alws.utils.errata import get_nevra, is_errata_package_matched

NAMES = ("kernel", "kernel-core", "glibc")
VERSIONS = ("4.18.0", "5.14.0")
RELEASES = (
    "553.el8_10",
    "553.el8_10.alma.1",
    "553.el8_10.alma",
    "554.el8_10",
    "1.module+el8.10.0+3897+0ad2a2d8.2",
    "1.module_el8.10.0+3900+aaaaaaaa.2",
)
ARCHES = ("x86_64", "aarch64", "i686", "noarch")


def make_rpms():
    # every second combination and no glibc-5.14.0 at all,
    # so some errata packages have no match
    return [
        {
            "name": name,
            "epoch": "0",
            "version": version,
            "release": release,
            "arch": arch,
            "artifact_href": f"/{name}/{version}/{release}/{arch}/",
        }
        for i, (name, version, release, arch) in enumerate(
            itertools.product(NAMES, VERSIONS, RELEASES, ARCHES)
        )
        if i % 2 and (name, version) != ("glibc", "5.14.0")
    ]


def make_errata_packages():
    return [
        SimpleNamespace(
            name=name,
            epoch=0,
            version=version,
            release=release,
            arch=arch,
            albs_packages=(
                [SimpleNamespace(status=ErrataPackageStatus.released)]
                if i % 7 == 0
                else []
            ),
        )
        for i, (name, version, release, arch) in enumerate(
            itertools.product(NAMES, VERSIONS, RELEASES, ARCHES)
        )
    ]


def test_errata_package_rpms_match_full_scan():
    rpms = make_rpms()
    grouped_rpms = AlmaLinuxReleasePlanner.group_rpms_for_errata(rpms)
    matched_any = False
    for errata_pkg in make_errata_packages():
        expected = [
            rpm for rpm in rpms if is_errata_package_matched(errata_pkg, rpm)
        ]
        matched_any = matched_any or bool(expected)
        assert (
            AlmaLinuxReleasePlanner.get_errata_package_rpms(
                errata_pkg,
                grouped_rpms,
            )
            == expected
        )
    assert matched_any


def test_missing_errata_packages_match_full_scan():
    rpms = make_rpms()
    record = SimpleNamespace(packages=make_errata_packages())
    expected = [
        get_nevra(errata_pkg, clean=False)
        for errata_pkg in record.packages
        if not any(is_errata_package_matched(errata_pkg, rpm) for rpm in rpms)
        and not any(
            albs_pkg.status == ErrataPackageStatus.released
            for albs_pkg in errata_pkg.albs_packages
        )
    ]

    missing = AlmaLinuxReleasePlanner.get_missing_errata_packages(
        record,
        AlmaLinuxReleasePlanner.group_rpms_for_errata(rpms),
    )

    assert missing == expected
    assert 0 < len(missing) < len(record.packages)

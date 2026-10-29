from contextlib import nullcontext as does_not_raise
from unittest.mock import MagicMock
from uuid import uuid4

import pytest

from alws import models
from alws.constants import ErrataReferenceType
from alws.crud.errata import sync_references_in_update_records
from alws.pulp_models import UpdateRecord, UpdateReference
from alws.utils.errata import (
    debrand_affected_cpe_list,
    debrand_comment,
    debrand_description_and_title,
    debrand_id,
    debrand_reference,
)


@pytest.mark.parametrize(
    "original_value, expected_value, exception",
    [
        pytest.param(
            "oval:com.redhat.rhsa:tst:20231659022",
            "oval:org.almalinux.alsa:tst:20231659022",
            does_not_raise(),
            id="oval_id_0",
        ),
        pytest.param(
            "oval:com.redhat.rhsa:tst:20231659020",
            "oval:org.almalinux.alsa:tst:20231659020",
            does_not_raise(),
            id="oval_id_1",
        ),
        pytest.param(
            "oval:com.redhat.rhsa:obj:20231659007",
            "oval:org.almalinux.alsa:obj:20231659007",
            does_not_raise(),
            id="oval_id_2",
        ),
        pytest.param(
            "oval:com.redhat.rhsa:ste:20231659003",
            "oval:org.almalinux.alsa:ste:20231659003",
            does_not_raise(),
            id="oval_id_3",
        ),
        pytest.param(
            "oval:com.redhat.exc_test:ste:20231659003",
            "",
            pytest.raises(
                ValueError,
                match=r"^invalid OVAL identifier: .+",
            ),
            id="wrong_oval_id_0",
        ),
    ],
)
def test_debrand_oval_id(
    original_value,
    expected_value,
    exception,
):
    message = "Cannot debrand oval ID"
    with exception:
        assert debrand_id(original_value) == expected_value, message


@pytest.mark.parametrize(
    "ref, distro_version, expected_value",
    [
        pytest.param(
            {
                "id": "RHSA-2023:1659",
                "source": "RHSA",
                "url": "https://access.redhat.com/errata/RHSA-2023:1659",
            },
            "8",
            {
                "id": "ALSA-2023:1659",
                "source": "ALSA",
                "url": "https://errata.almalinux.org/8/ALSA-2023-1659.html",
            },
            id="errata_ref_0",
        ),
        pytest.param(
            {
                "id": "CVE-2022-2526",
                "source": "CVE",
                "url": "https://access.redhat.com/security/cve/CVE-2022-2526",
            },
            "8",
            {
                "id": "CVE-2022-2526",
                "source": "CVE",
                "url": "https://access.redhat.com/security/cve/CVE-2022-2526",
            },
            id="cve_ref_0",
        ),
        pytest.param(
            {
                "id": "ALSA-2022:5163",
                "source": "SELF_REF",
                "url": "https://errata.almalinux.org/8/ALSA-2022-5163.html",
            },
            "8",
            {
                "id": "ALSA-2022:5163",
                "source": "ALSA",
                "url": "https://errata.almalinux.org/8/ALSA-2022-5163.html",
            },
            id="self_ref_0",
        ),
    ],
)
def test_debrand_errata_reference(
    ref,
    distro_version,
    expected_value,
):
    message = "Cannot debrand errata reference"
    assert debrand_reference(ref, distro_version) == expected_value, message


@pytest.mark.parametrize(
    "comment, distro_version, expected_value",
    [
        pytest.param(
            "Red Hat Enterprise Linux must be installed",
            "8",
            "AlmaLinux must be installed",
            id="comment_0",
        ),
        pytest.param(
            "kernel is signed with Red Hat redhatrelease2 key",
            "8",
            "kernel is signed with AlmaLinux OS 8 key",
            id="comment_1",
        ),
        pytest.param(
            "kernel is signed with CentOS 8 key",
            "8",
            "kernel is signed with AlmaLinux OS 8 key",
            id="comment_2",
        ),
    ],
)
def test_debrand_oval_comment(
    comment,
    distro_version,
    expected_value,
):
    message = "Cannot debrand oval comment"
    assert debrand_comment(comment, distro_version) == expected_value, message


@pytest.mark.parametrize(
    "original_value, expected_value",
    [
        pytest.param(
            "RHSA-2023:1659: kpatch-patch security update (Important)",
            "ALSA-2023:1659: kpatch-patch security update (Important)",
            id="title_0",
        ),
        pytest.param(
            """
            Bug Fix(es) and Enhancement(s):
                * Update .NET 6.0 to SDK 6.0.107 and Runtime 6.0.7
                [rhel-8.6.0.z] (BZ#2105397)
            """,
            """
            Bug Fix(es) and Enhancement(s):
                * Update .NET 6.0 to SDK 6.0.107 and Runtime 6.0.7
                [rhel-8.6.0.z] (BZ#2105397)
            """,
            id="description_0",
        ),
        pytest.param(
            """
            Bug Fix(es):
                * [rhel8-rt] BUG: using __this_cpu_add() in preemptible
                [00000000] - caller is __mod_memcg_lruvec_state+0x69/0x1c0
                (BZ#2122600)
                * The latest RHEL 8.6.z4 kernel changes need to be merged
                into the RT source tree to keep source parity between
                the two kernels. (BZ#2125396)
            """,
            """
            Bug Fix(es):
                * [almalinux8-rt] BUG: using __this_cpu_add() in preemptible
                [00000000] - caller is __mod_memcg_lruvec_state+0x69/0x1c0
                (BZ#2122600)
                * The latest AlmaLinux 8.6.z4 kernel changes need to be merged
                into the RT source tree to keep source parity between
                the two kernels. (BZ#2125396)
            """,
            id="description_1",
        ),
        pytest.param(
            """
            For detailed information on changes in this release,
            see the Red Hat Enterprise Linux 8.1 Release Notes linked
            """,
            """
            For detailed information on changes in this release,
            see the AlmaLinux 8.1 Release Notes linked
            """,
            id="description_2",
        ),
        pytest.param(
            """
            For details on how to apply this update, which includes the changes
            described in this advisory, refer to: <https://access.redhat.com/articles/11258>
            Security Fix(es):

              * qemu-img can't create a qcow2 overlay with 'data_file' feature on top of a file without destroying the original image [rhel-9.8.z] (JIRA:RHEL-164549)
              * See access.redhat.com/security/updates/classification for RHEL details
            """,
            """
            For details on how to apply this update, which includes the changes
            described in this advisory, refer to: <https://access.redhat.com/articles/11258>
            Security Fix(es):

              * qemu-img can't create a qcow2 overlay with 'data_file' feature on top of a file without destroying the original image [rhel-9.8.z] (JIRA:RHEL-164549)
              * See access.redhat.com/security/updates/classification for AlmaLinux details
            """,
            id="description_urls_and_jira_ids",
        ),
        pytest.param(
            """
            * use -Dcom.redhat.fips=false (RHEL-118777, RHEL-118778)
            * D-Bus interface com.redhat.RHSM1 allows local privilege escalation
            * containers-common is missing RPM-GPG-KEY-redhat-beta
            * podman pull registry.redhat.io/rhel9/toolbox
            * An update for redhat-rpm-config is now available
            * [grafana / rhel-10.2.z] Remove Lua ExclusiveArch macro
            * [RHEL-9.8.z]: Update the mlx5 drivers, Unable to boot RHEL-8.6
            """,
            """
            * use -Dcom.redhat.fips=false (RHEL-118777, RHEL-118778)
            * D-Bus interface com.redhat.RHSM1 allows local privilege escalation
            * containers-common is missing RPM-GPG-KEY-redhat-beta
            * podman pull registry.redhat.io/rhel9/toolbox
            * An update for redhat-rpm-config is now available
            * [grafana / rhel-10.2.z] Remove Lua ExclusiveArch macro
            * [RHEL-9.8.z]: Update the mlx5 drivers, Unable to boot AlmaLinux-8.6
            """,
            id="description_identifiers",
        ),
        pytest.param(
            "module is now available for Red Hat Enterprise Linux 8.\n\n"
            "Red Hat Product Security has rated this update. "
            "In Red Hat Enterprise Linux 8 and Red Hat Enterprise Linux 9 "
            "systems, see the Red Hat Enterprise Linux 9 Release Notes",
            "module is now available for AlmaLinux 8.\n\n"
            "Red Hat Product Security has rated this update. "
            "In AlmaLinux 8 and AlmaLinux 9 "
            "systems, see the AlmaLinux 9 Release Notes",
            id="description_versions",
        ),
        pytest.param(
            "An update for httpd is now available for Red Hat Enterprise "
            "Linux 8, Red Hat Enterprise Linux 8.4 Extended Update Support "
            "and Red Hat Enterprise Linux 8.2 Update Services for\n"
            "SAP Solutions. The Red Hat build of OpenJDK packages rely on "
            "Red Hat Satellite and the Red Hat Customer Portal. "
            "The Red Hat support for this package is limited. "
            "Corosync provides C APIs for Red Hat cluster software.",
            "An update for httpd is now available for AlmaLinux 8, "
            "Red Hat Enterprise Linux 8.4 Extended Update Support "
            "and Red Hat Enterprise Linux 8.2 Update Services for\n"
            "SAP Solutions. The Red Hat build of OpenJDK packages rely on "
            "Red Hat Satellite and the Red Hat Customer Portal. "
            "The Red Hat support for this package is limited. "
            "Corosync provides C APIs for AlmaLinux cluster software.",
            id="description_products",
        ),
    ],
)
def test_debrand_errata_description_and_title(
    original_value,
    expected_value,
):
    message = "Cannot debrand errata description or title"
    assert (
        debrand_description_and_title(original_value) == expected_value
    ), message


@pytest.mark.parametrize(
    "cpe_list, distro_version, expected_value",
    [
        pytest.param(
            [
                "cpe:/a:redhat:enterprise_linux:8",
                "cpe:/a:redhat:enterprise_linux:8::appstream",
                "cpe:/a:redhat:enterprise_linux:8::crb",
                "cpe:/a:redhat:enterprise_linux:8::nfv",
            ],
            "8",
            [
                "cpe:/a:almalinux:almalinux:8",
                "cpe:/a:almalinux:almalinux:8::appstream",
                "cpe:/a:almalinux:almalinux:8::powertools",
                "cpe:/a:almalinux:almalinux:8::nfv",
            ],
            id="cpe_for_8_version_0",
        ),
        pytest.param(
            [
                "cpe:/a:redhat:enterprise_linux:9",
                "cpe:/a:redhat:enterprise_linux:9::appstream",
                "cpe:/a:redhat:enterprise_linux:9::crb",
                "cpe:/a:redhat:enterprise_linux:9::nfv",
            ],
            "9",
            [
                "cpe:/a:almalinux:almalinux:9",
                "cpe:/a:almalinux:almalinux:9::appstream",
                "cpe:/a:almalinux:almalinux:9::crb",
                "cpe:/a:almalinux:almalinux:9::nfv",
            ],
            id="cpe_for_9_version_0",
        ),
    ],
)
def test_debrand_oval_affected_cpe_list(
    cpe_list,
    distro_version,
    expected_value,
):
    message = "Cannot debrand oval affected cpe list"
    assert (
        debrand_affected_cpe_list(cpe_list, distro_version) == expected_value
    ), message


def test_sync_references_in_update_records():
    def pulp_ref(ref_type, ref_id):
        return UpdateReference(
            href=f"https://example.com/{ref_id}",
            ref_id=ref_id,
            title=ref_id,
            ref_type=ref_type,
        )

    def db_ref(ref_type, ref_id):
        return models.NewErrataReference(
            href=f"https://example.com/{ref_id}",
            ref_id=ref_id,
            title=ref_id,
            ref_type=ref_type,
        )

    stale_cve = pulp_ref("cve", "CVE-2099-0001")
    stale_bug = pulp_ref("bugzilla", "1")
    kept_cve = pulp_ref("cve", "CVE-2099-0002")
    # Only reference types mirroring upstream may be pruned
    kept_self = pulp_ref("self", "ALSA-2099:0001")
    pulp_record = UpdateRecord(
        references=[stale_cve, stale_bug, kept_cve, kept_self]
    )
    pulp_db = MagicMock()
    pulp_db.execute.return_value.scalars.return_value.first.return_value = (
        pulp_record
    )

    sync_references_in_update_records(
        pulp_db=pulp_db,
        errata_records=[
            {"pulp_href": f"/pulp/api/v3/content/rpm/advisories/{uuid4()}/"}
        ],
        references=[
            db_ref(ErrataReferenceType.cve, "CVE-2099-0002"),
            db_ref(ErrataReferenceType.cve, "CVE-2099-0003"),
            db_ref(ErrataReferenceType.rhsa, "RHSA-2099:0001"),
        ],
    )

    deleted = [call.args[0] for call in pulp_db.delete.call_args_list]
    assert deleted == [stale_cve, stale_bug]
    added = {
        (ref.ref_type, ref.ref_id)
        for ref in pulp_record.references
        if ref not in (stale_cve, stale_bug, kept_cve, kept_self)
    }
    assert added == {("cve", "CVE-2099-0003"), ("rhsa", "RHSA-2099:0001")}
    assert pulp_record.updated_date

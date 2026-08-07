import copy

import pytest

from alws.crud.errata import create_errata_record
from tests.mock_classes import BaseAsyncTestCase


@pytest.fixture
async def errata_refs_record(errata_create_payload):
    """Create a dedicated, uniquely-ided errata record for reference tests.

    A unique id avoids colliding with records other tests in this module leak
    (tables are module-scoped and ``create_errata_record`` commits its own
    session, so committed rows persist between tests).
    """
    payload = copy.deepcopy(errata_create_payload)
    payload["id"] = "ALSA-2022:9999"
    await create_errata_record(payload)
    return payload


@pytest.mark.usefixtures("base_platform")
class TestErrataEndpoints(BaseAsyncTestCase):
    async def test_record_create(
        self,
        errata_create_payload,
    ):
        response = await self.make_request(
            "post",
            "/api/v1/errata/",
            json=errata_create_payload,
        )
        message = f"Cannot create record:\n{response.text}"
        assert response.status_code == self.status_codes.HTTP_200_OK, message

    async def test_get_updateinfo_xml(
        self,
        list_updateinfo_records,
    ):
        response = await self.make_request(
            "get",
            "/api/v1/errata/ALSA-2023:1068/updateinfo/",
        )
        assert (
            response.status_code == self.status_codes.HTTP_200_OK
            and "xml version" in response.text
        ), f"Cannot get updateinfo.xml:\n{response.text}"

    async def test_list_errata_all_records(
        self,
        errata_create_payload,
        create_errata_dramatiq
    ):

        response = await self.make_request("get", "/api/v1/errata/all/")
        errata = response.json()
        assert (
            response.status_code == self.status_codes.HTTP_200_OK and errata
        ), f"Cannot get errata records:\n{response.text}"
        assert errata[0]['id'] == errata_create_payload["id"]
        assert errata[0]['platform_id'] == errata_create_payload["platform_id"]

    async def test_update_references_adds_missing_and_is_idempotent(
        self,
        errata_refs_record,
    ):
        record_id = errata_refs_record["id"]
        platform_id = errata_refs_record["platform_id"]
        existing_ref = errata_refs_record["references"][0]
        new_cve_ref = {
            "href": "https://access.redhat.com/security/cve/CVE-2099-0001",
            "ref_id": "CVE-2099-0001",
            "ref_type": "cve",
            "title": "CVE-2099-0001",
            "cve": {
                "id": "CVE-2099-0001",
                "cvss3": "CVSS:3.1/AV:N/AC:L/PR:N/UI:N/S:U/C:H/I:H/A:H",
                "cwe": None,
                "impact": "Important",
                "public": "2099-01-01T00:00:00Z",
            },
        }
        payload = {
            "errata_record_id": record_id,
            "errata_platform_id": platform_id,
            # existing_ref must be ignored (add-only), only the CVE is new
            "references": [existing_ref, new_cve_ref],
        }
        response = await self.make_request(
            "post",
            "/api/v1/errata/update_references/",
            json=payload,
        )
        message = f"Cannot update references:\n{response.text}"
        assert response.status_code == self.status_codes.HTTP_200_OK, message

        record = response.json()
        ref_ids = [ref["ref_id"] for ref in record["references"]]
        # the new CVE is added exactly once
        assert ref_ids.count("CVE-2099-0001") == 1, ref_ids
        # the pre-existing RHSA reference and the auto self-ref are preserved
        assert existing_ref["ref_id"] in ref_ids, ref_ids
        assert record_id in ref_ids, ref_ids

        # Posting the same payload again must be a no-op (add-only, dedup).
        response = await self.make_request(
            "post",
            "/api/v1/errata/update_references/",
            json=payload,
        )
        assert (
            response.status_code == self.status_codes.HTTP_200_OK
        ), response.text
        ref_ids_again = [
            ref["ref_id"] for ref in response.json()["references"]
        ]
        assert sorted(ref_ids_again) == sorted(ref_ids), ref_ids_again

    async def test_update_references_unknown_record(
        self,
        errata_create_payload,
    ):
        payload = {
            "errata_record_id": "ALSA-1999:0000",
            "errata_platform_id": errata_create_payload["platform_id"],
            "references": errata_create_payload["references"],
        }
        response = await self.make_request(
            "post",
            "/api/v1/errata/update_references/",
            json=payload,
        )
        assert (
            response.status_code == self.status_codes.HTTP_404_NOT_FOUND
        ), response.text

    async def test_list_errata_all_records_by_platform(
        self,
        errata_create_payload,
    ):
        platform_id = errata_create_payload['platform_id']
        response = await self.make_request(
            "get", f"/api/v1/errata/all/?platform_id={platform_id}"
        )
        assert (
            response.status_code == self.status_codes.HTTP_200_OK
            and response.json()
        ), f"Cannot get errata records by platform id:\n{response.text}"

        response = await self.make_request(
            "get", f"/api/v1/errata/all/?platform_id={platform_id + 1}"
        )
        assert (
            response.status_code == self.status_codes.HTTP_200_OK
            and not response.json()
        ), f"Cannot get errata records by platform id:\n{response.text}"

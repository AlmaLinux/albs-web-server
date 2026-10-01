import copy
import datetime
import uuid

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from alws import models
from alws.constants import ErrataReleaseStatus
from alws.crud.errata import ERRATA_RECORDS_PER_PAGE, create_errata_record
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


@pytest.mark.usefixtures("base_platform")
class TestErrataQueryPagination(BaseAsyncTestCase):
    """GET /errata/query/ must never return the whole table.

    The endpoint is unauthenticated and its non-compact branch eager-loads
    packages -> albs_packages -> build_artifacts -> build_tasks for every row,
    so an unpaginated call is the cheapest way to exhaust the API from
    outside. Records are created on a platform of their own so the assertions
    do not depend on what other tests in this module leaked.
    """

    RECORD_COUNT = 12

    @pytest.fixture
    async def isolated_errata_records(self, async_session: AsyncSession):
        suffix = uuid.uuid4().hex[:8]
        platform = models.Platform(
            name=f"errata-paging-{suffix}",
            type="rpm",
            distr_type="rhel",
            distr_version="9",
            test_dist_name="almalinux",
            arch_list=["x86_64"],
            data={},
            modularity={},
        )
        async_session.add(platform)
        await async_session.flush()
        issued = datetime.datetime(2024, 1, 1)
        async_session.add_all([
            models.NewErrataRecord(
                id=f"ALSA-2024:{9000 + number}",
                platform_id=platform.id,
                release_status=ErrataReleaseStatus.NOT_RELEASED,
                issued_date=issued + datetime.timedelta(days=number),
                updated_date=issued + datetime.timedelta(days=number),
                original_description="description",
                original_title="title",
                contact_mail="packager@almalinux.org",
                severity="Important",
                rights="Copyright",
            )
            for number in range(self.RECORD_COUNT)
        ])
        await async_session.commit()
        return platform.id

    async def test_query_without_page_returns_first_page(
        self,
        isolated_errata_records: int,
    ):
        response = await self.make_request(
            "get",
            f"/api/v1/errata/query/?platformId={isolated_errata_records}",
        )
        message = f"Cannot query errata records:\n{response.text}"
        assert response.status_code == self.status_codes.HTTP_200_OK, message
        payload = response.json()

        message = (
            f"Got {len(payload['records'])} records without a pageNumber; "
            "the endpoint is returning more than one page"
        )
        assert len(payload["records"]) == ERRATA_RECORDS_PER_PAGE, message
        assert payload["current_page"] == 1
        message = "total_records must still count every matching record"
        assert payload["total_records"] == self.RECORD_COUNT, message

    async def test_query_without_page_matches_explicit_first_page(
        self,
        isolated_errata_records: int,
    ):
        """Omitting pageNumber must be the same request as pageNumber=1.

        The response is an ErrataListResponse either way, so defaulting the
        page does not change the shape for a caller that omitted it - only
        the length of `records`.
        """
        implicit, explicit = [
            (
                await self.make_request(
                    "get",
                    f"/api/v1/errata/query/?platformId="
                    f"{isolated_errata_records}{suffix}",
                )
            ).json()
            for suffix in ("", "&pageNumber=1")
        ]
        assert implicit == explicit

    @pytest.mark.parametrize("page_number", [0, -5])
    async def test_query_clamps_pages_below_the_first(
        self,
        isolated_errata_records: int,
        page_number: int,
    ):
        """A bad page must not fall through to the unpaginated branch.

        `page and not count` treats 0 as "no pagination", and a negative page
        would build a negative OFFSET, so both are clamped to the first page.
        """
        response = await self.make_request(
            "get",
            f"/api/v1/errata/query/?platformId={isolated_errata_records}"
            f"&pageNumber={page_number}",
        )
        assert response.status_code == self.status_codes.HTTP_200_OK
        payload = response.json()
        assert len(payload["records"]) == ERRATA_RECORDS_PER_PAGE
        assert payload["current_page"] == 1

from datetime import datetime

import pytest

from tests.mock_classes import BaseAsyncTestCase


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
    ):
        response = await self.make_request("get", "/api/v1/errata/all/")
        errata = response.json()
        assert (
            response.status_code == self.status_codes.HTTP_200_OK and errata
        ), f"Cannot get errata records:\n{response.text}"
        assert errata[0]['id'] == errata_create_payload["id"]
        assert errata[0]['platform_id'] == errata_create_payload["platform_id"]

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

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

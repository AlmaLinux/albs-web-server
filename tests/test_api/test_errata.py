import pytest

from tests.mock_classes import BaseAsyncTestCase


@pytest.mark.usefixtures("base_platform")
class TestErrataEndpoints(BaseAsyncTestCase):
    async def test_record_create(self, errata_create_payload):
        response = await self.make_request(
            "post",
            "/api/v1/errata/",
            json=errata_create_payload,
        )
        message = f"Cannot create record:\n{response.text}"
        assert response.status_code == self.status_codes.HTTP_200_OK, message

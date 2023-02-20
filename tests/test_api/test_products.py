import pytest

from tests.mock_classes import BaseAsyncTestCase


@pytest.mark.usefixtures(
    "create_base_platform",
    "create_repo",
)
class TestProductsEndpoints(BaseAsyncTestCase):
    async def test_product_create(self, product_create_payload):
        response = await self.make_request(
            "post",
            "/api/v1/products/",
            json=product_create_payload,
        )
        message = f"Cannot create product:\n{response.text}"
        assert response.status_code == self.status_codes.HTTP_200_OK, message

import pytest

from alws.models import Product
from tests.mock_classes import BaseAsyncTestCase


@pytest.mark.usefixtures(
    "base_platform",
    "create_repo"
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


    async def test_product_remove(
        self,
        user_product: Product,
        get_rpm_distros,
        delete_by_href
    ):
        endpoint = f"/api/v1/products/{user_product.id}/remove/"
        response = await self.make_request(
            "delete",
            endpoint
        )
        message = f"Cannot remove product:\n{response.text}"
        assert response.status_code == self.status_codes.HTTP_200_OK, message


    async def test_add_to_product(
        self,
        regular_build,
        product_create_payload,
    ):
        product_name = product_create_payload['name']
        build_id = regular_build.id
        endpoint = f"/api/v1/products/add/{build_id}/{product_name}/"
        response = await self.make_request(
            "post",
            endpoint
        )

        message = f"Cannot add build to product:\n{response.text}"
        assert response.status_code == self.status_codes.HTTP_200_OK, message

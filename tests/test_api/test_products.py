from fastapi import status

from tests.mock_classes import BaseAsyncTestCase


class TestProductsEndpoints(BaseAsyncTestCase):
    async def test_product_create(self):
        data = {
            "name": "AlmaLinux",
            "owner_id": self.user_id,
            "title": "AlmaLinux",
            "description": "",
            "platforms": [
                {
                    "id": 1,
                    "name": "AlmaLinux-8",
                    "distr_type": "rhel",
                    "distr_version": "8",
                    "arch_list": [
                        "i686",
                        "x86_64",
                        "ppc64le",
                        "aarch64",
                        "s390x",
                    ],
                    "modularity": {},
                },
            ],
            "is_community": True,
        }
        response = await self.make_request(
            "post",
            "/api/v1/products/",
            json=data,
        )
        message = f"product isn't created, status_code: {response.status_code}"
        assert response.status_code == status.HTTP_200_OK, message

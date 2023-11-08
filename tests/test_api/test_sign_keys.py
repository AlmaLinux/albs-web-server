from tests.mock_classes import BaseAsyncTestCase


class TestSignKeys(BaseAsyncTestCase):
    async def test_create_new_key_incorrect_platform(
        self, basic_sign_key_payload
    ):
        payload = basic_sign_key_payload.copy()
        payload["platform_id"] = 9999
        response = await self.make_request(
            "post", f"/api/v1/sign-keys/new/", json=payload
        )
        assert response.status_code == self.status_codes.HTTP_400_BAD_REQUEST
        assert response.json()["detail"].startswith('No platform with id')

    async def test_create_new_key_already_exists(
        self, sign_key, basic_sign_key_payload
    ):
        response = await self.make_request(
            "post", f"/api/v1/sign-keys/new/", json=basic_sign_key_payload
        )
        err_msg = f"Key with keyid {sign_key.keyid} already exists"
        assert response.status_code == self.status_codes.HTTP_400_BAD_REQUEST
        assert response.json()["detail"] == err_msg

    async def test_create_new_key_with_platform(
        self, base_platform, basic_sign_key_payload
    ):
        payload = basic_sign_key_payload.copy()
        payload["platform_id"] = base_platform.id
        response = await self.make_request(
            "post", f"/api/v1/sign-keys/new/", json=payload
        )
        assert response.status_code == self.status_codes.HTTP_201_CREATED

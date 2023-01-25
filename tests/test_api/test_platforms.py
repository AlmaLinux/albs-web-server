from tests.mock_classes import BaseAsyncTestCase


class TestPlatformsEndpoints(BaseAsyncTestCase):
    async def test_platform_create(self):
        platform = {
            "name": "test_platform111",
            "type": "rpm",
            "distr_type": "rpm",
            "distr_version": "test",
            "test_dist_name": "test_dist_name",
            "arch_list": ["1", "2"],
            "repos": [
                {
                    "name": "test_repo",
                    "arch": "rpm",
                    "url": "http://",
                    "type": "rpm",
                    "debug": False,
                }
            ],
            "data": {"test": "test"},
        }

        response = await self.make_request(
            "post",
            "/api/v1/platforms/",
            json=platform,
        )
        message = f"Cannot create platform:\n{response.text}"
        assert response.status_code == self.status_codes.HTTP_200_OK, message

from fastapi import status

from tests.mock_classes import BaseAsyncTestCase


class TestCrudClass(BaseAsyncTestCase):
    def test_empty_tasks(self):
        response = self.make_request(
            "post",
            "/api/v1/build_node/ping",
            json={"active_tasks": []},
        )
        message = "Empty active_tasks aren't pinged"
        self.assertEqual(response.status_code, status.HTTP_200_OK, message)

    def test_ping(self):
        response = self.make_request(
            "post",
            "/api/v1/build_node/ping",
            json={"active_tasks": [1, 2, 3]},
        )
        message = "Tasks aren't pinged"
        self.assertEqual(response.status_code, status.HTTP_200_OK, message)

    def test_platform_create(self):
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

        response = self.make_request(
            "post",
            "/api/v1/platforms/",
            json=platform,
        )
        message = f"platform isn't created, status_code: {response.status_code}"
        self.assertEqual(response.status_code, status.HTTP_200_OK, message)

    def test_product_create(self):
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
        response = self.make_request(
            "post",
            "/api/v1/products/",
            json=data,
        )
        message = f"product isn't created, status_code: {response.status_code}"
        print(response.text)
        self.assertEqual(response.status_code, status.HTTP_200_OK, message)

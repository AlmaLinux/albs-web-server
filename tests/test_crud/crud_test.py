import unittest

from fastapi.testclient import TestClient
from unittest import mock

from alws.app import app
from alws.utils import jwt_utils
from alws.config import settings


class CustomDB(unittest.TestCase):
    def custom_db(self):
        class MockedDB(mock.Mock):
            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc_val, exc_tb):
                pass

            def begin(self):
                return self

            def refresh(self, platform):
                platform.id = 1
                return platform

        return MockedDB()


class TestPingTasks(CustomDB):

    client = TestClient(app)
    token = jwt_utils.generate_JWT_token(
        {'user_id': 1},
        settings.jwt_secret,
        'HS256'
    )

    def test_empy_tasks(self):
        
        response = self.client.post(
            "/api/v1/build_node/ping",
            headers={"Authorization": f"Bearer {self.token}"},
            json={'active_tasks': []}
        )
        message = "Empty active_tasks aren't pinged"
        self.assertEqual(response.status_code, 200, message)

    def test_db_call(self):
        with mock.patch('build_node.get_sync_db') as get_sync_db_mock:
            get_sync_db_mock.return_value = self.custom_db()
            response = self.client.post(
                "/api/v1/build_node/ping",
                headers={"Authorization": f"Bearer {self.token}"},
                json={'active_tasks': [1, 2, 3]}
            )
            message = "Tasks aren't pinged"
            self.assertEqual(response.status_code, 200, message)


class TestCreatePlatform(CustomDB):

    client = TestClient(app)
    token = jwt_utils.generate_JWT_token(
        {'user_id': 1},
        settings.jwt_secret,
        'HS256'
    )

    def test_db_call(self):
        with mock.patch('platforms.get_sync_db') as get_sync_db_mock:
            get_sync_db_mock.return_value = self.custom_db()
            platform = {
                'name': 'test_platform111',
                'type': 'rpm',
                'distr_type': 'rpm',
                'distr_version': 'test',
                'test_dist_name': 'test_dist_name',
                'arch_list': ['1', '2'],
                'repos': [{
                    'name': 'test_repo',
                    'arch': 'rpm',
                    'url': 'http://',
                    'type': 'rpm',
                    'debug': False,
                    }],
                'data': {'test': 'test'}
            }

            response = self.client.post(
                "/api/v1/platforms/",
                headers={"Authorization": f"Bearer {self.token}"},
                json=platform
            )
            message = "platform isn't created, " \
                      f"status_code: {response.status_code}"
            self.assertEqual(response.status_code, 200, message)

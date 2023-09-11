from alws.scripts.tests_cacher.tests_cacher import TestsCacher
from tests.mock_classes import BaseAsyncTestCase


class TestTestsCacher(BaseAsyncTestCase):
    async def test_tests_cacher(
        self,
        create_test_repository_payload: dict,
        mock_tests_cacher_make_request,
        mock_tests_cacher_get_repo_content,
    ):
        await self.make_request(
            'post',
            '/api/v1/test_repositories/create/',
            json=create_test_repository_payload,
        )
        tests_cacher = TestsCacher(
            albs_jwt_token=self.token,
            albs_api_url='http://localhost:8080',
            sleep_timeout=1,
        )
        await tests_cacher.run(dry_run=True)
        response = await self.make_request(
            'get',
            '/api/v1/test_repositories/1/',
        )
        assert (
            len(response.json()['packages']) > 0
        ), 'There is no processed test folders'

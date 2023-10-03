from typing import Dict, List, Union

import pytest

from tests.mock_classes import BaseAsyncTestCase


class TestRepositoriesEndpoints(BaseAsyncTestCase):
    async def test_create_test_repository(
        self,
        create_test_repository_payload: dict,
    ):
        response = await self.make_request(
            'post',
            '/api/v1/test_repositories/create/',
            json=create_test_repository_payload,
        )
        assert (
            response.status_code == self.status_codes.HTTP_200_OK
        ), self.get_assertion_message(
            response.text,
            'Cannot create test_repository:',
        )

    @pytest.mark.parametrize(
        'param_name, param_value',
        [
            pytest.param('', '', id='without_params'),
            pytest.param('pageNumber', '1', id='with_page_number'),
            pytest.param('name', 'mock_test_repo', id='with_repo_name'),
            pytest.param('id', '1', id='with_repo_id'),
        ],
    )
    async def test_get_test_repositories(
        self,
        param_name: str,
        param_value: str,
    ):
        query = ''
        if param_name in ('pageNumber', 'name'):
            query = f'?{param_name}={param_value}'
        if param_name == 'id':
            query = f'{param_value}/'
        response = await self.make_request(
            'get',
            f'/api/v1/test_repositories/{query}',
        )
        assert (
            response.status_code == self.status_codes.HTTP_200_OK
        ), self.get_assertion_message(
            response.text,
            'Cannot get repositories:',
        )

    async def test_update_test_repository(self):
        response = await self.make_request(
            'patch',
            '/api/v1/test_repositories/1/',
            json={
                'tests_dir': 'foo/',
                'tests_prefix': 'bar',
            },
        )
        assert (
            response.status_code == self.status_codes.HTTP_204_NO_CONTENT
        ), self.get_assertion_message(
            response.text,
            'Cannot update test repository:',
        )

    @pytest.mark.parametrize(
        'param_name, param_value',
        [
            pytest.param(
                'create',
                {
                    'package_name': 'mock1',
                    'folder_name': 'mock1',
                    'url': 'http://mock.com/mock1/',
                },
                id='with_one_package',
            ),
            pytest.param(
                'bulk_create',
                [
                    {
                        'package_name': 'mock2',
                        'folder_name': 'mock2',
                        'url': 'http://mock.com/mock2/',
                    },
                    {
                        'package_name': 'mock3',
                        'folder_name': 'mock3',
                        'url': 'http://mock.com/mock3/',
                    },
                ],
                id='with_many_packages',
            ),
        ],
    )
    async def test_create_test_package_mapping(
        self,
        param_name: str,
        param_value: Union[Dict[str, str], List[Dict[str, str]]],
    ):
        response = await self.make_request(
            'post',
            f'/api/v1/test_repositories/1/packages/{param_name}/',
            json=param_value,
        )
        assert (
            response.status_code == self.status_codes.HTTP_201_CREATED
        ), self.get_assertion_message(
            response.text,
            'Cannot create test package mapping:',
        )

    @pytest.mark.parametrize(
        'param_name, param_value',
        [
            pytest.param(
                'remove',
                '1',
                id='with_one_package',
            ),
            pytest.param(
                'bulk_delete',
                [
                    2,
                    3,
                ],
                id='with_many_packages',
            ),
        ],
    )
    async def test_remove_test_package_mapping(
        self,
        param_name: str,
        param_value: Union[Dict[str, str], List[int]],
    ):
        endpoint = f'/api/v1/test_repositories/packages/{param_value}/remove/'
        if param_name == 'bulk_delete':
            endpoint = '/api/v1/test_repositories/1/packages/bulk_remove/'
        response = await self.make_request(
            'post' if param_name == 'bulk_delete' else 'delete',
            endpoint,
            json=param_value if param_name == 'bulk_delete' else None,
        )
        assert (
            response.status_code == self.status_codes.HTTP_204_NO_CONTENT
        ), self.get_assertion_message(
            response.text,
            'Cannot remove test package mapping:',
        )

    async def test_remove_test_repository(self):
        response = await self.make_request(
            'delete',
            '/api/v1/test_repositories/1/remove/',
        )
        assert (
            response.status_code == self.status_codes.HTTP_204_NO_CONTENT
        ), self.get_assertion_message(
            response.text,
            'Cannot remove test repository:',
        )

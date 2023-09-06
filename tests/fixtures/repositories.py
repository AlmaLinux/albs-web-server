from typing import Any, Dict

import aiohttp
import pytest

from alws.scripts.tests_cacher.tests_cacher import TestsCacher
from tests.mock_classes import BaseAsyncTestCase


@pytest.fixture
def create_test_repository_payload() -> Dict[str, Any]:
    return {
        'name': 'mock_test_repo',
        'url': 'https://repo.almalinux.org/',
        'tests_dir': 'almalinux/',
        'tests_prefix': '8.',
    }


@pytest.mark.anyio
@pytest.fixture
def mock_tests_cacher_make_request(monkeypatch):
    async def func(*args, **kwargs):
        return_text = kwargs.pop('return_text', False)
        response = await BaseAsyncTestCase().make_request(**kwargs)
        if return_text:
            return response.text
        return response.json()

    monkeypatch.setattr(
        TestsCacher,
        'make_request',
        func,
    )


@pytest.mark.anyio
@pytest.fixture
def mock_tests_cacher_get_repo_content(monkeypatch):
    async def func(*args, **kwargs) -> str:
        repo_content = ''
        *_, endpoint = args
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(endpoint) as response:
                    response.raise_for_status()
                    repo_content = await response.text()
        except Exception:
            pass
        return repo_content

    monkeypatch.setattr(TestsCacher, 'get_test_repo_content', func)

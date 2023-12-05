from typing import Any, Dict

import pytest


@pytest.fixture
def create_test_repository_payload() -> Dict[str, Any]:
    return {
        'name': 'mock_test_repo',
        'url': 'https://repo.almalinux.org/',
        'tests_dir': 'almalinux/',
        'tests_prefix': '8.',
    }

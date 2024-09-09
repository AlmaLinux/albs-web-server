from typing import Any, Dict

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from alws.models import Repository


@pytest.fixture
def repo_for_upload_payload() -> Dict[str, Any]:
    return {
        'name': 'almalinux-8-appstream-x86_64',
        'arch': 'x86_64',
        'url': 'https://repo.almalinux.org/',
        'type': 'rpm',
        'debug': False,
    }


@pytest.fixture
def create_test_repository_payload() -> Dict[str, Any]:
    return {
        'name': 'mock_test_repo',
        'url': 'https://repo.almalinux.org/',
        'tests_dir': 'almalinux/',
        'tests_prefix': '8.',
        'team_id': 1,
    }


@pytest.fixture
async def repository_for_product(
    async_session: AsyncSession, repo_for_upload_payload: Dict[str, Any]
):
    repo = (
        (
            await async_session.execute(
                select(Repository).where(
                    Repository.name == repo_for_upload_payload['name'],
                )
            )
        )
        .scalars()
        .first()
    )
    if not repo:
        repo = Repository(**repo_for_upload_payload)
        async_session.add(repo)
        await async_session.commit()
    yield repo

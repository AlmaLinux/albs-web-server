from typing import List, Optional

import pytest

from scripts.migrate_repos_layout import (
    RPM_PUBLICATIONS_ENDPOINT,
    migrate_repositories,
    migrate_repository,
)
from tests.test_utils.pulp_utils import get_latest_repo_version, get_repo_href

FLAT = 'flat'
NESTED = 'nested_alphabetically'
NO_PUBLICATION = object()


class FakePulp:
    def __init__(
        self,
        repo_layout: Optional[str] = None,
        published_layout=None,
    ):
        self.repo_href = get_repo_href()
        self.repo = {
            'name': 'almalinux-9-baseos-x86_64',
            'layout': repo_layout,
            'latest_version_href': get_latest_repo_version(self.repo_href),
        }
        self.published_layout = published_layout
        self.updates: List[dict] = []
        self.publications: List[str] = []
        self.publication_queries: List[dict] = []

    async def get_by_href(self, href: str) -> dict:
        assert href == self.repo_href
        return dict(self.repo)

    async def update_rpm_repository(self, href: str, **attributes):
        assert href == self.repo_href
        self.updates.append(attributes)
        self.repo.update(attributes)

    async def request(self, method: str, endpoint: str, params=None, **_):
        assert (method, endpoint) == ('GET', RPM_PUBLICATIONS_ENDPOINT)
        self.publication_queries.append(params)
        if self.published_layout is NO_PUBLICATION:
            return {'count': 0, 'results': []}
        return {'count': 1, 'results': [{'layout': self.published_layout}]}

    async def create_rpm_publication(self, href: str):
        assert href == self.repo_href
        self.publications.append(href)
        # Pulp publishes with the repository layout
        self.published_layout = self.repo['layout']


@pytest.mark.anyio
async def test_migrate_nested_repository():
    pulp = FakePulp(repo_layout=None, published_layout=NESTED)
    result = await migrate_repository(pulp, pulp.repo_href, FLAT)
    assert result.layout_updated
    assert result.republished
    assert pulp.updates == [{'layout': FLAT}]
    assert pulp.publications == [pulp.repo_href]
    assert pulp.publication_queries[0]['repository_version'] == (
        pulp.repo['latest_version_href']
    )


@pytest.mark.anyio
async def test_migrate_is_idempotent():
    pulp = FakePulp(repo_layout=None, published_layout=NESTED)
    await migrate_repository(pulp, pulp.repo_href, FLAT)
    result = await migrate_repository(pulp, pulp.repo_href, FLAT)
    assert not result.layout_updated
    assert not result.republished
    assert pulp.updates == [{'layout': FLAT}]
    assert pulp.publications == [pulp.repo_href]


@pytest.mark.anyio
async def test_migrate_republishes_repository_with_layout_set():
    # e.g. a previous run was made with --no-publish
    pulp = FakePulp(repo_layout=FLAT, published_layout=NESTED)
    result = await migrate_repository(pulp, pulp.repo_href, FLAT)
    assert not result.layout_updated
    assert result.republished
    assert not pulp.updates
    assert pulp.publications == [pulp.repo_href]


@pytest.mark.anyio
async def test_migrate_publishes_unpublished_repository():
    pulp = FakePulp(repo_layout=None, published_layout=NO_PUBLICATION)
    result = await migrate_repository(pulp, pulp.repo_href, FLAT)
    assert result.layout_updated
    assert result.republished
    assert pulp.publications == [pulp.repo_href]


@pytest.mark.anyio
async def test_migrate_without_publishing():
    pulp = FakePulp(repo_layout=None, published_layout=NESTED)
    result = await migrate_repository(pulp, pulp.repo_href, FLAT, publish=False)
    assert result.layout_updated
    assert not result.republished
    assert pulp.updates == [{'layout': FLAT}]
    assert not pulp.publication_queries
    assert not pulp.publications


@pytest.mark.anyio
async def test_migrate_dry_run_changes_nothing():
    pulp = FakePulp(repo_layout=None, published_layout=NESTED)
    result = await migrate_repository(pulp, pulp.repo_href, FLAT, dry_run=True)
    assert result.layout_updated
    assert result.republished
    assert not pulp.updates
    assert not pulp.publications
    assert pulp.repo['layout'] is None


@pytest.mark.anyio
async def test_migrate_repositories_continues_after_failure():
    broken_href = get_repo_href()

    class PartiallyBrokenPulp(FakePulp):
        async def get_by_href(self, href: str) -> dict:
            if href == broken_href:
                raise RuntimeError('Pulp is down')
            return await super().get_by_href(href)

    pulp = PartiallyBrokenPulp(repo_layout=None, published_layout=NESTED)
    results = await migrate_repositories(
        pulp,
        [broken_href, pulp.repo_href],
        FLAT,
    )
    assert results[0] is None
    assert results[1].layout_updated
    assert results[1].republished
    assert pulp.publications == [pulp.repo_href]

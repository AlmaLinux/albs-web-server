import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
import yaml

from alws import models
from alws.schemas import (
    repository_schema,
    platform_schema,
)

from tests.fixtures.pulp import get_repo_href


@pytest.mark.anyio
@pytest.fixture
async def create_base_platform(async_session: AsyncSession):
    with open("reference_data/platforms.yaml", "rt") as file:
        loader = yaml.Loader(file)
        platform_data = loader.get_data()[0]
    schema = platform_schema.PlatformCreate(**platform_data).dict()
    schema["repos"] = []
    platform = (
        (
            await async_session.execute(
                select(models.Platform).where(
                    models.Platform.name == schema["name"],
                )
            )
        )
        .scalars()
        .first()
    )
    if platform:
        return
    platform = models.Platform(**schema)
    for repo in platform_data.get("repositories", []):
        repo["url"] = repo["remote_url"]
        repo["pulp_href"] = get_repo_href()
        repository = models.Repository(
            **repository_schema.RepositoryCreate(**repo).dict()
        )
        platform.repos.append(repository)
    async_session.add(platform)
    await async_session.commit()

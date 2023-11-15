from typing import AsyncIterable

import pytest
import yaml
from alws import models
from alws.schemas import platform_schema, repository_schema
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from tests.test_utils.pulp_utils import get_repo_href


@pytest.mark.anyio
@pytest.fixture
async def base_platform(
    session: AsyncSession,
) -> AsyncIterable[models.Platform]:
    with open("reference_data/platforms.yaml", "rt") as file:
        loader = yaml.Loader(file)
        platform_data = loader.get_data()[0]
    schema = platform_schema.PlatformCreate(**platform_data).model_dump()
    schema["repos"] = []
    platform = (
        (
            await session.execute(
                select(models.Platform).where(
                    models.Platform.name == schema["name"],
                )
            )
        )
        .scalars()
        .first()
    )
    if not platform:
        platform = models.Platform(**schema)
        for repo in platform_data.get("repositories", []):
            repo["url"] = repo["remote_url"]
            repo["pulp_href"] = get_repo_href()
            repository = models.Repository(
                **repository_schema.RepositoryCreate(**repo).model_dump()
            )
            platform.repos.append(repository)
        session.add(platform)
        await session.commit()
    yield platform

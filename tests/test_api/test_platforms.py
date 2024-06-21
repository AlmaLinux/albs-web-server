from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from alws.models import Platform, Repository
from tests.mock_classes import BaseAsyncTestCase


class TestPlatformsEndpoints(BaseAsyncTestCase):
    async def test_platform_create(self):
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
                },
            ],
            "data": {"test": "test"},
        }

        response = await self.make_request(
            "post",
            "/api/v1/platforms/",
            json=platform,
        )
        message = f"Cannot create platform:\n{response.text}"
        assert response.status_code == self.status_codes.HTTP_200_OK, message

    async def test_add_repositories_to_platform(
        self,
        base_platform,
        repository_for_product,
        async_session: AsyncSession,
    ):
        payload = [repository_for_product.id]
        response = await self.make_request(
            "patch",
            f"/api/v1/platforms/{base_platform.id}/add-repositories",
            json=payload,
        )
        message = f"Cannot add repositories to the platform:\n{response.text}"
        assert response.status_code == self.status_codes.HTTP_200_OK, message

        resulting_repo = (
            (
                await async_session.execute(
                    select(Repository).where(
                        Repository.id == repository_for_product.id
                    )
                )
            )
            .scalars()
            .first()
        )
        assert resulting_repo.platform_id == base_platform.id

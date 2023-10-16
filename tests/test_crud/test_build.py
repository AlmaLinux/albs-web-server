from alws.crud import build

from tests.mock_classes import BaseAsyncTestCase


class TestBuildCrud(BaseAsyncTestCase):

    async def test_build_delete(
        self,
        session,
        base_platform,
        base_product,
        create_errata,
        build_done,
        build_for_release,
    ):
        await session.close()
        await build.remove_build_job(session, build_for_release.id)

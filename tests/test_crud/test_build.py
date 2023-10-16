from sqlalchemy import select

from alws.crud import build
from alws.models import ErrataToALBSPackage

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
        res = (await session.execute(select(ErrataToALBSPackage))).scalars().all()
        print(res)
        await session.close()
        await build.remove_build_job(session, build_for_release.id)

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from alws.dramatiq.products import _perform_product_modification
from alws.models import Build, Product
from tests.mock_classes import BaseAsyncTestCase


@pytest.mark.usefixtures(
    "base_platform",
    "create_repo",
)
class TestProductsEndpoints(BaseAsyncTestCase):
    async def test_product_create(
        self,
        product_create_payload,
        create_file_repository,
    ):
        response = await self.make_request(
            "post",
            "/api/v1/products/",
            json=product_create_payload,
        )
        message = self.get_assertion_message(
            response.text,
            "Cannot create product:",
        )
        assert response.status_code == self.status_codes.HTTP_200_OK, message

    async def test_add_platfroms_to_product(
        self,
        user_product: Product,
        add_platfroms_to_product_payload,
    ):
        endpoint = f"/api/v1/products/{user_product.id}/add_platforms/"
        response = await self.make_request(
            "post",
            endpoint,
            json=add_platfroms_to_product_payload,
        )

        assert response.status_code == self.status_codes.HTTP_201_CREATED

    async def test_add_to_product(
        self,
        regular_build: Build,
        user_product: Product,
        async_session: AsyncSession,
    ):
        product_id = user_product.id
        product_name = user_product.name
        build_id = regular_build.id
        endpoint = f"/api/v1/products/add/{build_id}/{product_name}/"
        response = await self.make_request("post", endpoint)

        message = self.get_assertion_message(
            response.text,
            "Cannot add build to product:",
        )
        assert response.status_code == self.status_codes.HTTP_200_OK, message

        # dramatic.Actor.send is monkeypatched to return None.
        # That's why we manually call _perform_product_modification here.
        # In case there's an error in add_to_product, it will be raised and
        # the test will be reported as failed.
        await _perform_product_modification(build_id, product_id, "add")
        await async_session.commit()
        await async_session.refresh(user_product, attribute_names=['builds'])
        assert user_product.builds[0].id == build_id, message

    async def test_remove_from_product(
        self,
        user_product: Product,
        async_session: AsyncSession,
    ):
        product_id = user_product.id
        product_name = user_product.name
        # We remove the build created in the previous test
        build_id = 1
        endpoint = f"/api/v1/products/remove/{build_id}/{product_name}/"
        response = await self.make_request("post", endpoint)

        message = self.get_assertion_message(
            response.text,
            "Cannot remove build from product:",
        )
        assert response.status_code == self.status_codes.HTTP_200_OK, message
        await _perform_product_modification(build_id, product_id, "remove")
        db_product = (
            (
                await async_session.execute(
                    select(Product)
                    .where(Product.id == product_id)
                    .options(selectinload(Product.builds))
                )
            )
            .scalars()
            .first()
        )

        # At this point, db_product shouldn't have any build
        assert not db_product.builds, message

    async def test_user_product_remove_when_build_is_running(
        self,
        async_session: AsyncSession,
        user_product: Product,
        regular_build_with_user_product: Build,
    ):
        endpoint = f"/api/v1/products/{user_product.id}/remove/"
        response = await self.make_request("delete", endpoint)
        assert (
            response.status_code == self.status_codes.HTTP_400_BAD_REQUEST
        ), response.text
        # we need to delete active build for further product deletion
        for task in regular_build_with_user_product.tasks:
            await async_session.delete(task)
        await async_session.delete(regular_build_with_user_product)
        await async_session.commit()

    async def test_user_product_remove(
        self,
        user_product: Product,
        get_rpm_distros,
        delete_by_href,
    ):
        endpoint = f"/api/v1/products/{user_product.id}/remove/"
        response = await self.make_request("delete", endpoint)
        message = self.get_assertion_message(
            response.text,
            "Cannot remove product:",
        )
        assert response.status_code == self.status_codes.HTTP_200_OK, message

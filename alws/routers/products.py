import typing

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    status,
)

from alws import database
from alws.auth import get_current_user
from alws.crud import products, sign_task
from alws.dependencies import get_db
from alws.models import User
from alws.schemas import product_schema, sign_schema


public_router = APIRouter(
    prefix='/products',
    tags=['products'],
)

router = APIRouter(
    prefix='/products',
    tags=['products'],
    dependencies=[Depends(get_current_user)]
)


@public_router.get('/', response_model=typing.Union[
    typing.List[product_schema.Product], product_schema.ProductResponse])
async def get_products(
    pageNumber: int = None,
    search_string: str = None,
    db: database.Session = Depends(get_db),
):
    return await products.get_products(
        db, page_number=pageNumber, search_string=search_string)


@router.post('/', response_model=product_schema.Product)
async def create_product(
    product: product_schema.ProductCreate,
    db: database.Session = Depends(get_db),
):
    async with db.begin():
        db_product = await products.create_product(db, product)
        await db.commit()
    return await products.get_products(db, product_id=db_product.id)


@public_router.get('/{product_id}/', response_model=product_schema.Product)
async def get_product(
    product_id: int,
    db: database.Session = Depends(get_db),
):
    db_product = await products.get_products(db, product_id=product_id)
    if db_product is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f'Product with {product_id=} is not found'
        )
    return db_product


@router.post('/{product_id}/create-sign-key/',
             response_model=sign_schema.GenSignKeyTask)
async def create_product_sign_key(
        product_id: int,
        db: database.Session = Depends(get_db),
        user: User = Depends(get_current_user)
):
    product = await products.get_products(db, product_id=product_id)
    if not product.is_community:
        raise HTTPException(
            status_code=400,
            detail='Sign keys can be generated only for community products'
        )
    task = await sign_task.create_gen_key_task(db, user.id, product_id)
    await db.commit()
    return task


@public_router.post('/add/{build_id}/{product}/',
                    response_model=typing.Dict[str, bool])
async def add_to_product(
    product: str,
    build_id: int,
    db: database.Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    await products.modify_product(
        db, build_id, product, user.id, 'add')
    return {'success': True}


@public_router.post('/remove/{build_id}/{product}/',
                    response_model=typing.Dict[str, bool])
async def remove_from_product(
    product: str,
    build_id: int,
    db: database.Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    await products.modify_product(
        db, build_id, product, user.id, 'remove')
    return {'success': True}


@public_router.delete('/{product_id}/remove/',
                      status_code=status.HTTP_204_NO_CONTENT)
async def remove_product(
    product_id: int,
    db: database.Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    return await products.remove_product(db, product_id, user.id)

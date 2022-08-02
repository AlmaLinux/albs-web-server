import typing

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    status,
)

from alws import database
from alws.auth import get_current_user
from alws.crud import products
from alws.dependencies import get_db
from alws.errors import ProductError
from alws.schemas import product_schema


router = APIRouter(
    prefix='/products',
    tags=['products'],
    dependencies=[Depends(get_current_user)]
)


@router.get('/', response_model=typing.Union[
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
    db: database.Session = Depends(get_db)
):
    async with db.begin():
        try:
            db_product = await products.create_product(db, product)
        except ProductError as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=str(exc),
            )
        await db.commit()
    return await products.get_products(db, product_id=db_product.id)


@router.get('/{product_id}/', response_model=product_schema.Product)
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


@router.post('/add/{build_id}/{product}/',
             response_model=typing.Dict[str, bool])
async def add_to_product(
    product: str,
    build_id: int,
    db: database.Session = Depends(get_db)
):
    try:
        await products.modify_product(
            db, build_id, product, 'add')
        return {'success': True}
    except ProductError as error:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                            detail=str(error))


@router.post('/remove/{build_id}/{product}/',
             response_model=typing.Dict[str, bool])
async def remove_from_product(
    product: str,
    build_id: int,
    db: database.Session = Depends(get_db)
):
    try:
        await products.modify_product(
            db, build_id, product, 'remove')
        return {'success': True}
    except ProductError as error:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                            detail=str(error))


@router.delete('/{product_id}/remove/', status_code=status.HTTP_204_NO_CONTENT)
async def remove_product(
    product_id: int,
    db: database.Session = Depends(get_db),
):
    return await products.remove_product(db, product_id)

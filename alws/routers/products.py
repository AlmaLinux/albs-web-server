import typing

from fastapi import APIRouter, Depends

from alws import database
from alws.crud import products
from alws.dependencies import get_db, JWTBearer
from alws.schemas import product_schema


router = APIRouter(
    prefix='/products',
    tags=['products'],
    dependencies=[Depends(JWTBearer())]
)


@router.get('/', response_model=typing.List[product_schema.Product])
async def get_products(db: database.Session = Depends(get_db)):
    return await products.get_products(db)

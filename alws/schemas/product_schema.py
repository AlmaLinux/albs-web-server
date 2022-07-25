from pydantic import BaseModel


__all__ = ['ProductCreate']


class ProductCreate(BaseModel):
    name: str
    team_id: int
    owner_id: int


class Product(BaseModel):
    id: int
    name: str

    class Config:
        orm_mode = True

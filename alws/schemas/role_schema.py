from pydantic import BaseModel

__all__ = ['Role']


class Role(BaseModel):
    id: int
    name: str

    class Config:
        from_attributes = True

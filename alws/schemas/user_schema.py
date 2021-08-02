from pydantic import BaseModel


__all__ = ['User', 'LoginGithub']


class LoginGithub(BaseModel):

    code: str


class LoginResponse(BaseModel):

    id: int
    username: str
    email: str
    jwt_token: str

    class Config:
        orm_mode = True


class User(BaseModel):

    id: int
    username: str
    email: str

    class Config:
        orm_mode = True

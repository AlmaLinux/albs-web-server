import typing

from pydantic import BaseModel, AnyHttpUrl


class PackageTestRepository(BaseModel):
    id: int
    package_name: str
    folder_name: str
    url: str

    class Config:
        orm_mode = True


class PackageTestRepositoryCreate(BaseModel):
    package_name: str
    folder_name: str
    url: str


class TestRepository(BaseModel):
    id: int
    name: str
    url: AnyHttpUrl
    tests_dir: str
    tests_prefix: typing.Optional[str]
    packages: typing.Optional[typing.List[PackageTestRepository]]

    class Config:
        orm_mode = True


class TestRepositoryCreate(BaseModel):
    name: str
    url: AnyHttpUrl
    tests_dir: str
    tests_prefix: typing.Optional[str]


class TestRepositoryUpdate(BaseModel):
    tests_dir: typing.Optional[str]
    tests_prefix: typing.Optional[str]


class TestRepositoryResponse(BaseModel):
    test_repositories: typing.List[TestRepository]
    total_test_repositories: typing.Optional[int]
    current_page: typing.Optional[int]

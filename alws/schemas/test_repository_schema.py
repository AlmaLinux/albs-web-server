import typing

from pydantic import AnyHttpUrl, BaseModel, validator


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

    @validator('tests_dir', pre=True)
    def tests_dir_validator(cls, tests_dir: str):
        if not tests_dir.endswith('/'):
            raise ValueError('tests_dir field should ends with "/"')
        return tests_dir


class TestRepositoryUpdate(BaseModel):
    tests_dir: typing.Optional[str]
    tests_prefix: typing.Optional[str]

    @validator('tests_dir', pre=True)
    def tests_dir_validator(cls, tests_dir: str):
        if not tests_dir.endswith('/'):
            raise ValueError('tests_dir field should ends with "/"')
        return tests_dir


class TestRepositoryResponse(BaseModel):
    test_repositories: typing.List[TestRepository]
    total_test_repositories: typing.Optional[int]
    current_page: typing.Optional[int]

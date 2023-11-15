import typing

from pydantic import (
    AfterValidator,
    AnyHttpUrl,
    BaseModel,
    field_serializer,
    field_validator,
)
from typing_extensions import Annotated

AnyHttpUrlString = Annotated[AnyHttpUrl, AfterValidator(lambda v: str(v))]


class PackageTestRepository(BaseModel):
    id: int
    package_name: str
    folder_name: str
    url: str

    class Config:
        from_attributes = True


class PackageTestRepositoryCreate(BaseModel):
    package_name: str
    folder_name: str
    url: str


class TestRepository(BaseModel):
    id: int
    name: str
    url: AnyHttpUrlString
    tests_dir: str
    tests_prefix: typing.Optional[str] = None
    packages: typing.Optional[typing.List[PackageTestRepository]] = None

    class Config:
        from_attributes = True


class TestRepositoryCreate(BaseModel):
    name: str
    url: AnyHttpUrlString
    tests_dir: str
    tests_prefix: typing.Optional[str] = None

    @field_validator('tests_dir', mode="before")
    def tests_dir_validator(cls, tests_dir: str):
        if not tests_dir.endswith('/'):
            raise ValueError('tests_dir field should ends with "/"')
        return tests_dir


class TestRepositoryUpdate(BaseModel):
    tests_dir: typing.Optional[str] = None
    tests_prefix: typing.Optional[str] = None

    @field_validator('tests_dir', mode="before")
    def tests_dir_validator(cls, tests_dir: str):
        if not tests_dir.endswith('/'):
            raise ValueError('tests_dir field should ends with "/"')
        return tests_dir


class TestRepositoryResponse(BaseModel):
    test_repositories: typing.List[TestRepository]
    total_test_repositories: typing.Optional[int] = None
    current_page: typing.Optional[int] = None

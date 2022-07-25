import enum
import re
import typing
from collections import namedtuple

from dataclasses import dataclass


__all__ = [
    'DEFAULT_PRODUCT',
    'DEFAULT_TEAM',
    'DRAMATIQ_TASK_TIMEOUT',
    'REQUEST_TIMEOUT',
    'SYSTEM_USER_NAME',
    'BuildTaskStatus',
    'BuildTaskRefType',
    'ExportStatus',
    'Permissions',
    'PermissionTriad',
    'ReleaseStatus',
    'RepoType',
    'SignStatus',
    'TestTaskStatus',
    'debuginfo_regex',
]


REQUEST_TIMEOUT = 60  # 1 minute
DRAMATIQ_TASK_TIMEOUT = 36000000  # 10 hours in milliseconds
SYSTEM_USER_NAME = 'base_user'
DEFAULT_PRODUCT = 'AlmaLinux'
DEFAULT_TEAM = 'almalinux'


class Permissions(enum.IntFlag):
    DELETE = 1
    WRITE = 2
    READ = 4


@dataclass
class PermissionTriad:
    owner: Permissions
    group: Permissions
    other: Permissions


class BuildTaskStatus(enum.IntEnum):

    IDLE = 0
    STARTED = 1
    COMPLETED = 2
    FAILED = 3
    EXCLUDED = 4

    @classmethod
    def is_finished(cls, status):
        return status not in (cls.IDLE, cls.STARTED)


class TestTaskStatus(enum.IntEnum):
    CREATED = 1
    STARTED = 2
    COMPLETED = 3
    FAILED = 4


class TestCaseStatus(enum.IntEnum):
    FAILED = 1
    DONE = 2
    TODO = 3
    SKIPPED = 4


class ReleaseStatus(enum.IntEnum):
    SCHEDULED = 1
    IN_PROGRESS = 2
    COMPLETED = 3
    FAILED = 4


class SignStatus(enum.IntEnum):
    IDLE = 1
    IN_PROGRESS = 2
    COMPLETED = 3
    FAILED = 4


class BuildTaskRefType(enum.IntEnum):
    GIT_BRANCH = 1
    GIT_TAG = 2
    SRPM_URL = 3
    GIT_REF = 4

    @classmethod
    def from_text(cls, value: str) -> int:
        return int(build_ref_str_mapping[value])

    @classmethod
    def to_text(cls, value: int) -> str:
        return build_ref_int_mapping[value]


class ExportStatus(enum.IntEnum):
    NEW = 0
    IN_PROGRESS = 1
    COMPLETED = 2
    FAILED = 3


class SignStatusEnum(enum.IntEnum):
    SUCCESS = 1
    READ_ERROR = 2
    NO_SIGNATURE = 3
    WRONG_SIGNATURE = 4


build_ref_str_mapping: typing.Dict[str, int] = {
    'git_branch': BuildTaskRefType.GIT_BRANCH,
    'git_tag': BuildTaskRefType.GIT_TAG,
    'srpm_url': BuildTaskRefType.SRPM_URL,
    'git_ref': BuildTaskRefType.GIT_REF
}

build_ref_int_mapping: typing.Dict[int, str] = {
    value: key for key, value in build_ref_str_mapping.items()
}

debuginfo_regex = re.compile(r'debug(info|source)')

RepoType = namedtuple('RepoType', ('name', 'arch', 'debug'))
PackageNevra = namedtuple('PackageNevra',
                          ('name', 'epoch', 'version', 'release', 'arch'))

import enum
import re
import typing
from collections import namedtuple


__all__ = ['BuildTaskStatus', 'ReleaseStatus', 'TestTaskStatus',
           'BuildTaskRefType', 'SignStatus', 'RepoType', 'ExportStatus',
           'debuginfo_regex']


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

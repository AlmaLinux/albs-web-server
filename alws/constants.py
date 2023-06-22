import enum
import re
import typing
from collections import namedtuple
from dataclasses import dataclass

__all__ = [
    "DEFAULT_PRODUCT",
    "DEFAULT_TEAM",
    "DRAMATIQ_SIGN_TASK_TIMEOUT",
    "DRAMATIQ_GEN_KEY_TASK_TIMEOUT",
    "DEFAULT_FILE_CHUNK_SIZE",
    "LOWEST_PRIORITY",
    "REQUEST_TIMEOUT",
    "SYSTEM_USER_NAME",
    "UPLOAD_FILE_CHUNK_SIZE",
    "BuildTaskStatus",
    "BuildTaskRefType",
    "ExportStatus",
    "ErrataPackageStatus",
    "ErrataReferenceType",
    "ErrataReleaseStatus",
    "PackageNevra",
    "Permissions",
    "PermissionTriad",
    "ReleaseStatus",
    "RepoType",
    "SignStatus",
    "TestTaskStatus",
    "debuginfo_regex",
]


REQUEST_TIMEOUT = 60  # 1 minute
DRAMATIQ_SIGN_TASK_TIMEOUT = 60 * 60 * 1000  # 1 hour in milliseconds
DRAMATIQ_GEN_KEY_TASK_TIMEOUT = 10 * 60 * 1000  # 10 minutes in milliseconds
DEFAULT_FILE_CHUNK_SIZE = 1024 * 1024  # 1 MB
UPLOAD_FILE_CHUNK_SIZE = 50 * 1024 * 1024  # 50 MB
SYSTEM_USER_NAME = "base_user"
DEFAULT_PRODUCT = "AlmaLinux"
DEFAULT_TEAM = "almalinux"
# Release constants
LOWEST_PRIORITY = 10


class Permissions(enum.IntFlag):
    DELETE = 1
    WRITE = 2
    READ = 4


@dataclass
class PermissionTriad:
    owner: Permissions
    group: Permissions
    other: Permissions


class ReleasePackageTrustness(enum.IntEnum):
    UNKNOWN = 0
    MAXIMUM = 1
    MEDIUM = 2
    LOWEST = 10

    @classmethod
    def decrease(cls, trustness: int) -> int:
        if trustness == cls.LOWEST:
            return trustness
        if trustness == cls.MAXIMUM:
            trustness = cls.MEDIUM
        elif trustness == cls.MEDIUM:
            trustness = cls.LOWEST
        return trustness


class BuildTaskStatus(enum.IntEnum):
    IDLE = 0
    STARTED = 1
    COMPLETED = 2
    FAILED = 3
    EXCLUDED = 4
    CANCELLED = 5

    @classmethod
    def is_finished(cls, status: int):
        return status not in (cls.IDLE, cls.STARTED)

    @classmethod
    def get_status_by_text(cls, text: str):
        status = cls.COMPLETED
        if text == "failed":
            status = cls.FAILED
        elif text == "excluded":
            status = cls.EXCLUDED
        elif text == "cancelled":
            status = cls.CANCELLED
        return status


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


class ErrataPackageStatus(enum.Enum):
    proposal = "proposal"
    skipped = "skipped"
    released = "released"
    approved = "approved"


class ErrataReferenceType(enum.Enum):
    cve = "cve"
    rhsa = "rhsa"
    self_ref = "self"
    bugzilla = "bugzilla"


class ErrataReleaseStatus(enum.Enum):
    NOT_RELEASED = "not released"
    IN_PROGRESS = "in progress"
    RELEASED = "released"
    FAILED = "failed"


class ReleaseStatus(enum.IntEnum):
    SCHEDULED = 1
    IN_PROGRESS = 2
    COMPLETED = 3
    FAILED = 4
    REVERTED = 5


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
    "git_branch": BuildTaskRefType.GIT_BRANCH,
    "git_tag": BuildTaskRefType.GIT_TAG,
    "srpm_url": BuildTaskRefType.SRPM_URL,
    "git_ref": BuildTaskRefType.GIT_REF,
}

build_ref_int_mapping: typing.Dict[int, str] = {
    value: key for key, value in build_ref_str_mapping.items()
}

debuginfo_regex = re.compile(r"debug(info|source)")

RepoType = namedtuple("RepoType", ("name", "arch", "debug"))
BeholderKey = namedtuple(
    "BeholderKey",
    ("name", "version", "arch", "is_beta", "is_devel"),
)
PackageNevra = namedtuple(
    "PackageNevra",
    ("name", "epoch", "version", "release", "arch"),
)

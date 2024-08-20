import enum
import re
import typing
from collections import namedtuple
from dataclasses import dataclass

__all__ = [
    "DEFAULT_PRODUCT",
    "DEFAULT_TEAM",
    "DRAMATIQ_TASK_TIMEOUT",
    "DRAMATIQ_GEN_KEY_TASK_TIMEOUT",
    "DEFAULT_FILE_CHUNK_SIZE",
    "LOWEST_PRIORITY",
    "REQUEST_TIMEOUT",
    "SYSTEM_USER_NAME",
    "UPLOAD_FILE_CHUNK_SIZE",
    "BeholderKey",
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
    "ReleasePackageTrustness",
    "RepoType",
    "SignStatus",
    "GenKeyStatus",
    "TestTaskStatus",
    "debuginfo_regex",
    "BeholderMatchMethod",
]


REQUEST_TIMEOUT = 60  # 1 minute
DRAMATIQ_TASK_TIMEOUT = 3 * 60 * 60 * 1000  # 3 hours in milliseconds
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
    """
    Enum representing the trustworthiness of a release package.
    The trustworthiness is shown in different colors
    on the web UI. The values correspond to:

    UNKNOWN (0): The trustworthiness of the package is unknown,
    represented in grey on the UI.
    MAXIMUM (1): The package has maximum trustworthiness,
    represented in green on the UI.
    MEDIUM (2): The package has medium trustworthiness,
    represented in yellow on the UI.
    LOWEST (3): The package has the lowest trustworthiness,
    represented in red on the UI.
    """

    UNKNOWN, MAXIMUM, MEDIUM, LOWEST = range(4)


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
    CANCELLED = 5


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


class ErrataPackagesType(enum.Enum):
    PROD = "prod"
    BUILD = "build"


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


class GenKeyStatus(enum.IntEnum):
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


class GitHubIssueStatus(enum.Enum):
    TODO = "Todo"
    DEVELOPMENT = "In Development"
    BUILDING = "Building"
    TESTING = "Testing"
    RELEASED = "Released"


class BeholderMatchMethod(enum.Enum):
    EXACT = "exact"
    CLOSEST = "closest"
    NAME_VERSION = "name_version"
    NAME_ONLY = "name_only"

    @classmethod
    def all(cls):
        return [
            cls.NAME_ONLY.value,
            cls.NAME_VERSION.value,
            cls.CLOSEST.value,
            cls.EXACT.value,
        ]

    @classmethod
    def green(cls):
        # as Andrew mentioned exact = green in the Web user interface
        return [cls.EXACT.value]

    @classmethod
    def yellow(cls):
        # as Andrew mentioned closest\name_version\name_only = yellow in the Web user interface
        return [cls.CLOSEST.value, cls.NAME_VERSION.value, cls.NAME_ONLY.value]


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

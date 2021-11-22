import enum


__all__ = ['BuildTaskStatus', 'ReleaseStatus', 'TestTaskStatus']


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


class ReleaseStatus(enum.IntEnum):
    SCHEDULED = 1
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
        cls_value = {
            'git_branch': cls.GIT_BRANCH,
            'git_tag': cls.GIT_TAG,
            'srpm_url': cls.SRPM_URL,
            'git_ref': cls.GIT_REF
        }[value]
        return int(cls_value)

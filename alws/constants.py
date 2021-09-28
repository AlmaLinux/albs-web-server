import enum


__all__ = ['BuildTaskStatus', 'TestTaskStatus']


class BuildTaskStatus(enum.IntEnum):

    IDLE = 0
    BUILD_STARTED = 1
    BUILD_COMPLETED = 2
    SIGN_STARTED = 3
    SIGN_COMPLETED = 4
    FAILED = 5
    EXCLUDED = 6

    @classmethod
    def is_finished(cls, status):
        return status not in (cls.IDLE, cls.STARTED)


class TestTaskStatus(enum.IntEnum):
    CREATED = 1
    STARTED = 2
    COMPLETED = 3
    FAILED = 4

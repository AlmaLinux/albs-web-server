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

import enum


__all__ = ['BuildTaskStatus', 'TestTaskStatus', 'SignTaskStatus']


class BuildTaskStatus(enum.IntEnum):

    IDLE = 0
    STARTED = 1
    COMPLETED = 2
    FAILED = 3
    EXCLUDED = 4

    @classmethod
    def is_finished(cls, status):
        return status not in (cls.IDLE, cls.STARTED)


class SignTaskStatus(enum.IntEnum):

    IDLE = 0
    PENDING = 1
    STARTED = 2
    COMPLETED = 3
    FAILED = 4
    EXCLUDED = 5

    @classmethod
    def is_finished(cls, status):
        return status not in (cls.IDLE, cls.COMPLETED)


class TestTaskStatus(enum.IntEnum):
    CREATED = 1
    STARTED = 2
    COMPLETED = 3
    FAILED = 4

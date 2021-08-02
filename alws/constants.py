import enum


__all__ = ['BuildTaskStatus']


class BuildTaskStatus(enum.IntEnum):

    IDLE = 0
    STARTED = 1
    COMPLETED = 2
    FAILED = 3

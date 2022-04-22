import re


__all__ = [
    'is_debuginfo_rpm'
]


def is_debuginfo_rpm(name: str) -> bool:
    regex = re.compile(r'-debug(info|source)(-|$)')
    return bool(regex.search(name))

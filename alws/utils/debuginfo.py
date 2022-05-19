import re


__all__ = [
    'clean_debug_name',
    'is_debuginfo_rpm',
]


def is_debuginfo_rpm(name: str) -> bool:
    regex = re.compile(r'-debug(info|source)(-|$)')
    return bool(regex.search(name))


def clean_debug_name(name: str) -> str:
    return re.sub(r'-debug(info|source|)$', '', name)

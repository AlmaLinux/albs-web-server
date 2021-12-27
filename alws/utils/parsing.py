import re


__all__ = ['parse_git_ref']

def parse_git_ref(pattern : str, git_ref : str):
    re_pattern = re.compile(pattern)
    match = re_pattern.search(git_ref)
    if match:
        return match.groups()[-1]
    else:
        return None
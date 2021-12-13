from pathlib import PurePath


__all__ = ['generate_repository_path']


def generate_repository_path(export_id: int, repo_name: str,
                             arch: str, debug: bool) -> PurePath:
    if debug:
        arch = f'{arch}-debug'
    return PurePath(str(export_id), repo_name, arch)
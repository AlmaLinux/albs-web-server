from pathlib import Path


__all__ = ['generate_repository_path']


def generate_repository_path(export_id: int, repo_name: str,
                             arch: str, debug: bool) -> Path:
    if debug:
        arch = f'{arch}-debug'
    return Path(str(export_id), repo_name, arch)

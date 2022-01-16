from pathlib import Path


__all__ = ['generate_repository_path']


def generate_repository_path(export_id: int, repo_name: str,
                             arch: str, debug: bool) -> Path:
    if debug:
        return Path(str(export_id), repo_name, 'debug', arch, 'Packages')
    elif arch == 'src':
        return Path(str(export_id), repo_name, 'Source', 'Packages')
    else:
        return Path(str(export_id), repo_name, arch, 'Packages')

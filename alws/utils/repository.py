from pathlib import Path


__all__ = ['generate_repository_path']


def generate_repository_path(repo_name: str, arch: str, debug: bool) -> Path:
    if debug:
        return Path(repo_name, 'debug', arch, 'Packages')
    elif arch == 'src':
        return Path(repo_name, 'Source', 'Packages')
    else:
        return Path(repo_name, arch, 'Packages')

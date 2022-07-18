from alws.config import settings

__all__ = ['generate_repo_config']


def generate_repo_config(
    repo: dict,
) -> str:
    config_template = (
        f"[copr:{settings.pulp_host}:{repo['owner']}:{repo['name']}]\n"
        f"name=Copr repo for {repo['name']} owned by {repo['owner']}\n"
        f"baseurl={repo['url']}\n"
        "type=rpm-md\n"
        "skip_if_unavailable=True\n"
        "gpgcheck=0\n"
        "enabled=1\n"
        "enabled_metadata=1\n"
    )
    return config_template

import typing

from alws.utils.pulp_client import PulpClient
from alws import models


__all__ = ['create_empty_repo']


async def create_empty_repo(
        pulp_client: PulpClient,
        distribution: models.Distribution
) -> typing.List[models.Repository]:
    distro_repos = []
    for platform in distribution.platforms:
        arches = ['src']
        arches.extend(platform.arch_list)
        for arch in arches:
            repo_name = f'{platform.name}-{arch}-{distribution.name}-dr'
            repo_url, pulp_href = await pulp_client.create_build_rpm_repo(
                repo_name)
            repo = models.Repository(
                name=repo_name,
                url=repo_url,
                arch=arch,
                pulp_href=pulp_href,
                type=arch)
            distribution.repositories.append(repo)
            distro_repos.append(repo)
    return distro_repos

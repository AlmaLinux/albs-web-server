import typing

from alws.utils.pulp_client import PulpClient
from alws import models


__all__ = ['create_empty_repo']


async def create_empty_repo(
        pulp_client: PulpClient,
        distribution: models.Distribution
) -> typing.List[models.Repository]:
    distro_repos = []
    distro_name = distribution.name
    for platform in distribution.platforms:
        arches = ['src'] + platform.arch_list
        for is_debug in (True, False):
            for arch in arches:
                if arch == 'src' and is_debug:
                    continue
                debug_suffix = '-debug' if is_debug else ''
                repo_name = (
                    f'{distro_name}-{platform.name}-{arch}{debug_suffix}-dr'
                )
                repo_url, pulp_href = await pulp_client.create_build_rpm_repo(
                    repo_name)
                repo = models.Repository(
                    name=repo_name,
                    url=repo_url,
                    arch=arch,
                    pulp_href=pulp_href,
                    type=arch,
                    debug=is_debug)
                distribution.repositories.append(repo)
                distro_repos.append(repo)
    return distro_repos

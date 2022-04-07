import asyncio

from alws.errors import ModuleUpdateError
from alws.utils.pulp_client import PulpClient


__all__ = ['get_rpm_package_info', 'update_module_index']


async def get_rpm_package_info(pulp_client: PulpClient, rpm_href: str) \
        -> (str, dict):
    """
    Helper function to be used as part of `asyncio.gather`
    to return information about RPM package from Pulp
    """
    info = await pulp_client.get_rpm_package(rpm_href)
    return rpm_href, info


async def update_module_index(module_index, pulp_client: PulpClient,
                              module_name: str, module_stream: str,
                              rpm_packages, multilib: bool = False):
    results = await asyncio.gather(*(get_rpm_package_info(
        pulp_client, rpm.href) for rpm in rpm_packages))
    packages_info = dict(results)
    try:
        if module_index.has_devel_module():
            module = module_index.get_module(f'{module_name}-devel')
        else:
            module = module_index.get_module(module_name, module_stream)
        for rpm in rpm_packages:
            rpm_package = packages_info[rpm.href]
            if multilib:
                module.add_multilib_rpm_artifact(rpm_package)
            else:
                module.add_rpm_artifact(rpm_package)
    except Exception as e:
        raise ModuleUpdateError('Cannot update module: %s', str(e)) from e

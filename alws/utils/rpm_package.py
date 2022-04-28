import typing

from alws.utils.pulp_client import PulpClient


__all__ = ['get_rpm_package_info']


async def get_rpm_package_info(pulp_client: PulpClient, rpm_href: str,
                               include_fields: typing.List[str] = None,
                               exclude_fields: typing.List[str] = None) \
        -> (str, dict):
    info = await pulp_client.get_rpm_package(
        rpm_href, include_fields=include_fields, exclude_fields=exclude_fields)
    return rpm_href, info

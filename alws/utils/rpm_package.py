import typing

from alws.schemas.build_node_schema import BuildDoneArtifact
from alws.utils.pulp_client import PulpClient


__all__ = ["get_rpm_package_info"]


async def get_rpm_package_info(
    pulp_client: PulpClient,
    artifact: BuildDoneArtifact,
    include_fields: typing.Optional[typing.List[str]] = None,
    exclude_fields: typing.Optional[typing.List[str]] = None,
) -> typing.Tuple[str, typing.Dict[str, typing.Any]]:
    info = await pulp_client.get_rpm_package(
        artifact.href,
        include_fields=include_fields,
        exclude_fields=exclude_fields,
    )
    return artifact.href, info

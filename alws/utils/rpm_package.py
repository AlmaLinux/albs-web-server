import typing

from alws.models import BuildTaskArtifact
from alws.pulp_models import RpmPackage
from alws.utils.pulp_utils import (
    get_rpm_packages_by_ids,
    get_uuid_from_pulp_href,
)

__all__ = ["get_rpm_packages_info"]


def get_rpm_packages_info(
    artifacts: typing.List[BuildTaskArtifact],
) -> typing.Dict[str, typing.Dict[str, typing.Any]]:
    pkg_fields = [
        RpmPackage.content_ptr_id,
        RpmPackage.name,
        RpmPackage.epoch,
        RpmPackage.version,
        RpmPackage.release,
        RpmPackage.arch,
        RpmPackage.rpm_sourcerpm,
    ]
    pulp_packages = get_rpm_packages_by_ids(
        [get_uuid_from_pulp_href(artifact.href) for artifact in artifacts],
        pkg_fields,
    )
    return {
        pkg.pulp_href: {
            "name": pkg.name,
            "epoch": pkg.epoch,
            "version": pkg.version,
            "release": pkg.release,
            "arch": pkg.arch,
            "rpm_sourcerpm": pkg.rpm_sourcerpm,
        }
        for _, pkg in pulp_packages.items()
    }

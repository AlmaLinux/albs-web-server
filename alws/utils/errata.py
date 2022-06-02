import re
from typing import List


def debrand_id(rec_id: str) -> str:
    """
    De-brands an RHEL element identifier.
    Args:
        rec_id: OVAL element identifier.
    Returns:
        De-branded OVAL element identifier.
    """
    re_rslt = re.search(
        r"^oval:(?P<org>[-.\w]+?)\."
        r"(?P<advisory>(rh|al)[bes]a):"
        r"(?P<rec_type>[a-z]+):(?P<idx>\d+)$",
        rec_id,
    )
    if not re_rslt:
        raise ValueError(f"invalid OVAL identifier: {rec_id}")
    data = re_rslt.groupdict()
    org = "org.almalinux"
    adv = f'al{data["advisory"][2:]}'
    return f'oval:{org}.{adv}:{data["rec_type"]}:{data["idx"]}'


def debrand_affected_cpe_list(
    cpe_list: List[str], distro_version
) -> List[str]:
    new_list = []
    for cpe in cpe_list:
        cpe = cpe.replace("redhat:enterprise_linux", "almalinux:almalinux")
        if distro_version == "8":
            cpe = cpe.replace("crb", "powertools")
        new_list.append(cpe)
    return new_list


def debrand_reference(ref: dict, distro_version: str) -> dict:
    match = re.search(r"([A-Z]+)-(\d+):(\d+)", ref["id"])
    if not match:
        return ref
    prefix, year, _id = match.groups()
    prefix = re.sub(r"^RH", "AL", prefix)
    suffix = f"{prefix}-{year}-{_id}.html"
    return {
        "id": f"{prefix}-{year}:{_id}",
        "url": f"https://errata.almalinux.org/{distro_version}/{suffix}",
        "source": "ALSA",
    }


def debrand_comment(comment: str, distro_version: str) -> str:
    comment = re.sub(
        r"is signed with Red Hat .*? key",
        f"is signed with AlmaLinux OS {distro_version} key",
        comment,
    )
    comment = comment.replace(
        "Red Hat Enterprise Linux must be installed",
        "AlmaLinux must be installed",
    )
    comment = comment.replace(
        f"Red Hat Enterprise Linux {distro_version} is installed",
        f"AlmaLinux {distro_version} is installed",
    )
    return comment

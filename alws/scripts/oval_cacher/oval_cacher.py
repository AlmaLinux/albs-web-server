import asyncio
import re
from typing import Dict

from alws.scripts.oval_cacher.schema import OvalDefinition, CVE
from alws.scripts.oval_cacher.albs_api import AlbsApiClient
from alws.scripts.oval_cacher.config import config
from alws.scripts.oval_cacher.security_api_client import SecurityApiClient
from alws.scripts.oval_cacher.schema import OvalDefinition


def extract_packages_from_definition(definition: OvalDefinition):
    packages = []
    evr_states = {state.id: state for state in definition.states if state.evr}
    for obj in definition.objects:
        raw_package = {"name": obj.name}
        state = next(
            evr_states[test.state.state_ref]
            for test in definition.tests
            if all(
                (
                    test.state,
                    test.object.object_ref == obj.id,
                )
            )
            and test.state.state_ref in evr_states
        )
        epoch, version, release = re.search(r"(\d+):(.*)-(.*)", state.evr).groups()
        raw_package["epoch"] = int(epoch)
        raw_package["version"] = version
        raw_package["release"] = release
        arches = state.arch or "aarch64|ppc64le|s390x|x86_64"
        for arch in arches.split("|"):
            package = raw_package.copy()
            package["arch"] = arch
            packages.append(package)
    return packages


async def mainloop():
    api = SecurityApiClient(config.base_security_api_url)
    albs_api = AlbsApiClient(config.albs_api_url, config.albs_jwt_token)
    # TODO: add a lot of logging
    while True:
        processed_errata_ids = set(
            re.sub(r"^AL", "RH", record)
            for record in await albs_api.list_errata_record_ids()
        )
        async for item in api.iter_oval_items():
            if item.RHSA in processed_errata_ids:
                continue
            oval_info, cvrf = await asyncio.gather(
                *(api.get_full_oval_info(item), api.get_cvrf(item))
            )
            if oval_info.definition is None:
                continue
            metadata = oval_info.definition.metadata
            advisory = metadata.advisory
            cves: Dict[str, CVE] = {}
            for ref in metadata.reference:
                if ref.source == "CVE":
                    cves[ref.ref_id] = await api.get_cve(ref.ref_id)
            payload = {
                # 'platform': ...
                "id": item.RHSA,
                "issued_date": str(advisory.issued.date),
                "updated_date": str(advisory.updated.date),
                "title": metadata.title,
                "description": metadata.description,
                "status": cvrf.document_tracking.status.lower(),
                "version": cvrf.document_tracking.version,
                "severity": item.severity,
                "rights": advisory.rights,
                # 'reboot_suggested': ???? (can we generate it, based on updated packages?)
                "definition_id": oval_info.definition.id,
                "definition_version": oval_info.definition.version,
                "definition_class": oval_info.definition.class_,
                "affected_cpe": advisory.affected_cpe_list,
                "criteria": oval_info.definition.criteria.dict(),
                "tests": [test.dict() for test in oval_info.tests],
                "objects": [obj.dict() for obj in oval_info.objects],
                "states": [state.dict() for state in oval_info.states],
                "references": [
                    {
                        "href": ref.ref_url,
                        "ref_id": ref.ref_id,
                        # title ????
                        "cve": {
                            "cvss3": cves[ref.ref_id].cvss3.cvss3_scoring_vector,
                            "cwe": cves[ref.ref_id].cwe,
                            "impact": cves[ref.ref_id].threat_severity.lower()
                            if cves[ref.ref_id].threat_severity
                            else "None",
                            "public": cves[ref.ref_id].public_date,
                        }
                        if ref.source == "CVE" and cves[ref.ref_id].cvss3
                        else None,
                    }
                    for ref in metadata.reference
                ],
                "packages": extract_packages_from_definition(oval_info),
            }
            await albs_api.insert_oval_record(payload)
        await asyncio.sleep(600)


if __name__ == "__main__":
    asyncio.run(mainloop())

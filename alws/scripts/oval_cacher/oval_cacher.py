import asyncio
import re
import sys
import logging

from alws.scripts.oval_cacher.schema import OvalDefinition
from alws.scripts.oval_cacher.albs_api import AlbsApiClient
from alws.scripts.oval_cacher.config import config
from alws.scripts.oval_cacher.security_api_client import SecurityApiClient
from alws.scripts.oval_cacher.schema import OvalDefinition


def setup_logger(log_level: int = logging.INFO) -> logging.Logger:
    logger = logging.getLogger("oval_cacher")
    logger.setLevel(log_level)
    stdout_handler = logging.StreamHandler(sys.stdout)
    formatter = logging.Formatter(
        "%(asctime)s [%(name)s] (%(levelname)s): %(message)s",
        "%d.%m.%Y %H:%M:%S",
    )
    stdout_handler.setFormatter(formatter)
    logger.addHandler(stdout_handler)
    return logger


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
        epoch, version, release = re.search(
            r"(\d+):(.*)-(.*)", state.evr
        ).groups()
        raw_package["epoch"] = int(epoch)
        raw_package["version"] = version
        raw_package["release"] = release
        raw_package["reboot_suggested"] = False
        arches = state.arch or "aarch64|ppc64le|s390x|x86_64"
        for arch in arches.split("|"):
            package = raw_package.copy()
            package["arch"] = arch
            packages.append(package)
    return packages


async def mainloop():
    log = setup_logger(logging.DEBUG)
    api = SecurityApiClient(config.base_security_api_url)
    albs_api = AlbsApiClient(config.albs_api_url, config.albs_jwt_token)
    while True:
        platforms = await albs_api.list_platforms()
        platform_versions = {}
        oval_cache = {}
        for platform in platforms:
            if platform["distr_type"] != "rhel":
                continue
            distr_version = platform["distr_version"]
            platform_versions[distr_version] = platform["id"]
            oval_cache[distr_version] = await api.load_oval_xml_cache(
                distr_version
            )
        processed_errata_ids = set(
            re.sub(r"^AL", "RH", record["id"])
            for record in await albs_api.list_oval_records()
        )
        async for item in api.iter_oval_items():
            if item.RHSA in processed_errata_ids:
                log.debug('Item "%s" already processed, skipping', item.RHSA)
                continue
            oval_info, cvrf = await asyncio.gather(
                api.get_full_oval_info(item), api.get_cvrf(item)
            )
            if oval_info.definition is None:
                continue
            metadata = oval_info.definition.metadata
            platform_id = None
            platform_version = None
            for platform in metadata.affected.platform:
                platform_version = re.search(
                    r"Red Hat Enterprise Linux (\d+)", platform
                )
                if not platform_version:
                    continue
                platform_version = platform_version.groups()[0]
                platform_id = platform_versions.get(platform_version)
            if platform_id is None:
                log.debug(
                    'Item "%s" has unknown platform version: %s, skipping',
                    item.RHSA,
                    platform_version,
                )
                continue
            xml_oval = oval_cache[platform_version]
            if item.RHSA not in xml_oval["definitions"]:
                log.debug(
                    'Item "%s" was not found in oval.xml files, skipping',
                    item.RHSA,
                )
                continue
            xml_oval_def = xml_oval["definitions"][item.RHSA]
            advisory = metadata.advisory
            refs = []
            for ref in metadata.reference:
                dict_ref = {
                    "href": ref.ref_url,
                    "ref_id": ref.ref_id,
                    "ref_type": ref.source.lower(),
                }
                refs.append(dict_ref)
                if ref.source == "CVE":
                    cve = await api.get_cve(ref.ref_id)
                    if not cve.cvss3:
                        continue
                    impact = "None"
                    if cve.threat_severity:
                        impact = cve.threat_severity.lower()
                    dict_ref["cve"] = {
                        "id": ref.ref_id,
                        "cvss3": cve.cvss3.cvss3_scoring_vector,
                        "cwe": cve.cwe,
                        "impact": impact,
                        "public": cve.public_date,
                    }
            for ref in advisory.bugzilla:
                refs.append(
                    {
                        "href": ref.href,
                        "ref_id": ref.id,
                        "ref_type": "bugzilla",
                    }
                )
            tests = []
            objects = []
            states = []
            variables = []
            criteria_list = xml_oval_def["criteria"][:]
            while criteria_list:
                new_criteria_list = []
                for criteria in criteria_list:
                    new_criteria_list.extend(criteria["criteria"])
                    for criterion in criteria["criterion"]:
                        test = xml_oval["tests"][criterion["ref"]]
                        tests.append(test)
                        obj_ref = test["object_ref"]
                        if obj_ref:
                            obj = xml_oval["objects"][obj_ref]
                            objects.append(obj)
                            if obj.get("instance_var_ref"):
                                variables.append(
                                    xml_oval["variables"][
                                        obj["instance_var_ref"]
                                    ]
                                )
                        if test["state_ref"]:
                            state = xml_oval["states"][test["state_ref"]]
                        states.append(state)
                criteria_list = new_criteria_list
            payload = {
                "platform_id": platform_id,
                "id": item.RHSA,
                "issued_date": str(advisory.issued.date),
                "updated_date": str(advisory.updated.date),
                "title": metadata.title,
                "description": metadata.description,
                "status": cvrf.document_tracking.status.lower(),
                "version": cvrf.document_tracking.version,
                "severity": item.severity,
                "rights": advisory.rights,
                "definition_id": oval_info.definition.id,
                "definition_version": oval_info.definition.version,
                "definition_class": oval_info.definition.class_,
                "affected_cpe": advisory.affected_cpe_list,
                "criteria": xml_oval_def["criteria"],
                "tests": tests,
                "objects": objects,
                "states": states,
                "variables": variables,
                "references": refs,
                "packages": extract_packages_from_definition(oval_info),
            }
            await albs_api.insert_oval_record(payload)
        log.info("All records cached, sleeping for 10 minutes")
        await asyncio.sleep(600)


if __name__ == "__main__":
    asyncio.run(mainloop())

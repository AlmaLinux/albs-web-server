import urllib.parse
from typing import List

import aiohttp

from alws.scripts.oval_cacher.schema import CVE, CVRF, OvalGenericInfo, OvalDefinition


class SecurityApiClient:
    def __init__(self, base_url: str):
        self.base_url = base_url
        self.oval_list_endpoint = urllib.parse.urljoin(base_url, "oval.json")

    async def make_request(self, request):
        async with request as response:
            response.raise_for_status()
            return await response.json()

    async def iter_oval_items(self) -> List[OvalGenericInfo]:
        page = 1
        while True:
            items = await self.make_request(
                aiohttp.request("get", self.oval_list_endpoint, params={"page": page})
            )
            for item in items:
                yield OvalGenericInfo(**item)
            page += 1

    async def get_full_oval_info(self, oval_item: OvalGenericInfo) -> OvalDefinition:
        request = aiohttp.request("get", oval_item.resource_url)
        response = (await self.make_request(request))["oval_definitions"]
        definition = response.pop("definitions")["definition"]
        objects = response.pop("objects")["rpminfo_object"]
        states = response.pop("states")["rpminfo_state"]
        tests = response.pop("tests")["rpminfo_test"]
        advisory = definition["metadata"]["advisory"]
        advisory["affected_cpe_list"] = advisory["affected_cpe_list"]["cpe"]
        return OvalDefinition(
            objects=objects,
            definition=definition,
            tests=tests,
            states=states,
            **response,
        )

    async def get_cve(self, cve_id: str):
        request = aiohttp.request(
            "get", urllib.parse.urljoin(self.base_url, f"cve/{cve_id}.json")
        )
        return CVE(**(await self.make_request(request)))

    async def get_cvrf(self, oval_item: OvalGenericInfo) -> CVRF:
        request = aiohttp.request(
            "get", urllib.parse.urljoin(self.base_url, f"cvrf/{oval_item.RHSA}.json")
        )
        return CVRF(**(await self.make_request(request))["cvrfdoc"])

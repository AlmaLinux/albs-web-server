import urllib.parse

import aiohttp


class AlbsApiClient:
    def __init__(self, base_url: str, jwt_token: str):
        self.base_url = base_url
        self.jwt_token = jwt_token
        self.auth_headers = {"authorization": f"Bearer {jwt_token}"}
        self.insert_oval_record_endpoint = urllib.parse.urljoin(base_url, "errata/")
        self.list_oval_records_endpoint = urllib.parse.urljoin(base_url, "errata/all/")
        self.list_platforms_endpoint = urllib.parse.urljoin(base_url, "platforms/")

    async def make_request(self, request):
        async with request as response:
            print(await response.json())
            response.raise_for_status()
            return await response.json()

    async def insert_oval_record(self, payload: dict):
        request = aiohttp.request(
            "post",
            self.insert_oval_record_endpoint,
            json=payload,
            headers=self.auth_headers,
        )
        return await self.make_request(request)

    async def list_oval_records(self):
        request = aiohttp.request(
            "get", self.list_oval_records_endpoint, headers=self.auth_headers
        )
        return []

    async def list_platforms(self):
        request = aiohttp.request(
            "get", self.list_platforms_endpoint, headers=self.auth_headers
        )
        return await self.make_request(request)

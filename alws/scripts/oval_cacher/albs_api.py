import urllib.parse

import aiohttp


class AlbsApiClient:
    def __init__(self, base_url: str, jwt_token: str):
        self.base_url = base_url
        self.jwt_token = jwt_token
        self.auth_headers = {"authorization": f"Bearer {jwt_token}"}
        self.insert_oval_record_endpoint = urllib.parse.urljoin(
            base_url, "errata/"
        )

    async def make_request(self, request):
        async with request as response:
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
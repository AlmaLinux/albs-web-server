import argparse
import asyncio
import logging
import os
import sys
import urllib.parse

import aiohttp

sys.path.append(os.path.dirname(os.path.dirname(__file__)))

logging.basicConfig(
    format="%(asctime)s %(levelname)-8s %(message)s",
    level=logging.INFO,
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[
        logging.StreamHandler(),
    ],
)


def parse_args():
    parser = argparse.ArgumentParser(
        "errata-releaser",
        description="Releases updateinfo records through ALBS API",
    )
    parser.add_argument(
        "-d",
        "--date",
        type=str,
        default="2022-11-01",
        required=False,
        help="Date for start releasing (default: '2022-11-01')",
    )
    parser.add_argument(
        "-u",
        "--base-url",
        type=str,
        default="http://web_server:8000/api/v1/",
        required=False,
        help="ALBS URL (default: 'http://web_server:8000/api/v1/')",
    )
    parser.add_argument(
        "-t",
        "--jwt-token",
        type=str,
        required=True,
        help="JWT token for ALBS web server",
    )
    parser.add_argument(
        "-a",
        "--auto-approve",
        action="store_true",
        default=False,
        required=False,
        help="Approves records that contains proposal packages (disabled by default)",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        default=False,
        required=False,
        help="Check records and their packages that can be released (disabled by default)",
    )
    return parser.parse_args()


class AlbsAPI:
    def __init__(
        self,
        base_url: str,
        jwt_token: str,
        latest_date: str,
    ):
        self.base_url = base_url
        self.latest_date = latest_date
        self.headers = {"authorization": f"Bearer {jwt_token}"}

    async def make_request(self, request):
        async with request as response:
            response.raise_for_status()
            return await response.json()

    async def get_errata_records(self):
        endpoint = "errata/query/"
        request = aiohttp.request(
            "get",
            urllib.parse.urljoin(self.base_url, endpoint),
            headers=self.headers,
            params={
                "status": "not released",
            },
        )
        response = await self.make_request(request)
        return [
            rec
            for rec in response["records"]
            if rec["updated_date"] >= self.latest_date
        ]

    async def release_record(
        self,
        record_id: str,
    ):
        endpoint = f"errata/release_record/{record_id}"
        request = aiohttp.request(
            "post",
            urllib.parse.urljoin(self.base_url, endpoint),
            headers=self.headers,
        )
        return await self.make_request(request)

    async def update_package_statuses(
        self,
        packages: list,
    ):
        endpoint = "errata/update_package_status/"
        request = aiohttp.request(
            "post",
            urllib.parse.urljoin(self.base_url, endpoint),
            headers=self.headers,
            json=packages,
        )
        return await self.make_request(request)

    def check_package_statuses(self, record: dict) -> list:
        result = []
        record_id = record["id"]
        for pkg in record["packages"]:
            source = pkg["source_srpm"]
            if not source:
                continue
            for albs_pkg in pkg["albs_packages"]:
                if (
                    albs_pkg["status"] != "proposal"
                    or not albs_pkg["build_id"]
                ):
                    continue
                result.append(
                    {
                        "errata_record_id": record_id,
                        "build_id": albs_pkg["build_id"],
                        "source": source,
                        "status": "approved",
                    }
                )
        return result


async def main():
    args = parse_args()
    albs_api = AlbsAPI(
        base_url=args.base_url,
        jwt_token=args.jwt_token,
        latest_date=args.date,
    )

    logging.info("Collecting not released errata records...")
    not_released_records = await albs_api.get_errata_records()
    logging.info(
        "Total amount not released records: %d",
        len(not_released_records),
    )
    for record in not_released_records:
        record_id = record["id"]
        not_approved_packages = albs_api.check_package_statuses(record)
        if not_approved_packages:
            logging.info("Record %s contains proposal packages", record_id)
        if args.check:
            logging.info("Record %s can be scheduled for release", record_id)
            continue
        if not_approved_packages and args.auto_approve:
            logging.info("Updating package statuses for %s", record_id)
            await albs_api.update_package_statuses(not_approved_packages)
        await albs_api.release_record(record_id)
        logging.info("Record %s scheduled for release", record_id)


if __name__ == "__main__":
    asyncio.run(main())

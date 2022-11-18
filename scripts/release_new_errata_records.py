import argparse
import asyncio
import datetime
import logging
import urllib.parse

import aiohttp

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
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "-d",
        "--date",
        type=str,
        default=datetime.date.today().strftime("%Y-%m-%d"),
        required=False,
        help="Date for start releasing",
    )
    parser.add_argument(
        "-u",
        "--base-url",
        type=str,
        default="http://web_server:8000/api/v1/",
        required=False,
        help="ALBS URL",
    )
    parser.add_argument(
        "-t",
        "--jwt-token",
        type=str,
        required=True,
        help="JWT token for ALBS web server",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        default=False,
        required=False,
        help="Check records and their packages that can be released",
    )
    parser.add_argument(
        "--bulk",
        action="store_true",
        default=False,
        required=False,
        help="Bulk records release",
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
        endpoint = f"errata/release_record/{record_id}/"
        request = aiohttp.request(
            "post",
            urllib.parse.urljoin(self.base_url, endpoint),
            headers=self.headers,
        )
        return await self.make_request(request)

    async def bulk_records_release(
        self,
        records_ids: list,
    ):
        endpoint = "errata/bulk_release_records/"
        request = aiohttp.request(
            "post",
            urllib.parse.urljoin(self.base_url, endpoint),
            headers=self.headers,
            json=records_ids,
        )
        return await self.make_request(request)

    def check_package_statuses(self, record: dict):
        result = []
        for pkg in record["packages"]:
            source = pkg["source_srpm"]
            if not source:
                continue
            for albs_pkg in pkg["albs_packages"]:
                if albs_pkg["status"] != "proposal" or not albs_pkg["build_id"]:
                    continue
                result.append(albs_pkg)
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
    records_ids = []
    for record in not_released_records:
        record_id = record["id"]
        not_approved_packages = albs_api.check_package_statuses(record)
        if not_approved_packages:
            logging.info(
                "Record %s contains proposal packages: %s",
                record_id,
                str(not_approved_packages),
            )
        if args.check:
            logging.info("Record %s can be scheduled for release", record_id)
            continue
        if args.bulk:
            records_ids.append(record_id)
            continue
        await albs_api.release_record(record_id)
        logging.info("Record %s scheduled for release", record_id)
    if args.bulk:
        await albs_api.bulk_records_release(records_ids)
        logging.info(
            "Following records scheduled for release: %s",
            str(records_ids),
        )


if __name__ == "__main__":
    asyncio.run(main())

import asyncio
import logging
import urllib.parse
import aiohttp
import os
import sys

sys.path.append(os.path.dirname(os.path.dirname(__file__)))

logging.basicConfig(
    format="%(asctime)s %(levelname)-8s %(message)s",
    level=logging.INFO,
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[
        logging.StreamHandler(),
    ],
)

BASE_URL = "http://web_server:8000/api/v1/"
LATEST_DATE = "2022-11-01"
JWT_TOKEN = ""
HEADERS = {
    "authorization": f"Bearer {JWT_TOKEN}",
}


async def make_request(request):
    async with request as response:
        response.raise_for_status()
        return await response.json()


async def get_errata_records():
    endpoint = "errata/query/"
    request = aiohttp.request(
        "get",
        urllib.parse.urljoin(BASE_URL, endpoint),
        headers=HEADERS,
        params={
            "status": "not released",
        },
    )
    response = await make_request(request)
    return [
        rec for rec in response["records"]
        if rec["updated_date"] >= LATEST_DATE
    ]


async def release_record(record_id: str):
    endpoint = f"errata/release_record/{record_id}"
    request = aiohttp.request(
        "post",
        urllib.parse.urljoin(BASE_URL, endpoint),
        headers=HEADERS,
    )
    return await make_request(request)


async def update_package_statuses(packages: list):
    endpoint = "errata/update_package_status/"
    request = aiohttp.request(
        "post",
        urllib.parse.urljoin(BASE_URL, endpoint),
        headers=HEADERS,
        json=packages,
    )
    return await make_request(request)


def check_package_statuses(record: dict) -> list:
    result = []
    record_id = record["id"]
    for pkg in record["packages"]:
        source = pkg["source_srpm"]
        if not source:
            continue
        for albs_pkg in pkg["albs_packages"]:
            if albs_pkg["status"] != "proposal" or not albs_pkg["build_id"]:
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
    logging.info("Collecting not released errata records...")
    not_released_records = await get_errata_records()
    logging.info(
        "Total amount not released records: %d",
        len(not_released_records),
    )
    for record in not_released_records:
        record_id = record["id"]
        not_approved_packages = check_package_statuses(record)
        if not_approved_packages:
            logging.info("Updating package statuses for %s", record_id)
            await update_package_statuses(not_approved_packages)
        await release_record(record_id)
        logging.info("Record %s scheduled for release", record_id)


if __name__ == "__main__":
    asyncio.run(main())

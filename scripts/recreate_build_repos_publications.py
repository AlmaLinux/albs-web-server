import argparse
import os
import sys

from syncer import sync
from sqlalchemy.future import select
from sqlalchemy import or_

sys.path.append(os.path.dirname(os.path.dirname(__file__)))

from alws.database import Session
from alws.models import Repository
from alws.utils.pulp_client import PulpClient


def parse_args():
    parser = argparse.ArgumentParser('recreate_publications')
    parser.add_argument('-i', '--build-id', metavar='build_ids',
                        type=str, nargs='+', required=True,
                        help='List of build ids to re-generate'
                             'repositories publications')
    parser.add_argument('--pulp-host', type=str, required=True)
    parser.add_argument('-u', '--pulp-user', type=str, required=True)
    parser.add_argument('-p', '--pulp-password', type=str, required=True)
    return parser.parse_args()


async def recreate_publications(args):
    name_conditions = [
        Repository.name.like(f'%{b_id}%') for b_id in args.build_ids
    ]

    async with Session() as db:
        query = select(Repository.pulp_href).where(
            Repository.type == 'rpm',
            Repository.production.is_(False),
            or_(*name_conditions)
        )
        result = await db.execute(query)
        repo_hrefs = [item for (item,) in result.scalars().all()]

    pulp_client = PulpClient(args.pulp_host, args.pulp_user, args.pulp_password)
    for href in repo_hrefs:
        await pulp_client.create_rpm_publication(href)


def main():
    args = parse_args()
    sync(recreate_publications(args))
    return 0


if __name__ == '__main__':
    main()

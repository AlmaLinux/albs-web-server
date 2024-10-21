import os
import re
import sys

sys.path.append(os.path.dirname(os.path.dirname(__file__)))

from fastapi_sqla import open_session
from sqlalchemy import select
from sqlalchemy.orm import joinedload

from alws.models import Product
from alws.utils.fastapi_sqla_setup import sync_setup


def main():
    sync_setup()
    with open_session() as session:
        for product in (
            session.execute(
                select(Product)
                .where(Product.is_community.is_(True))
                .options(
                    joinedload(Product.repositories),
                    joinedload(Product.platforms),
                )
            )
            .scalars()
            .unique()
            .all()
        ):
            if not product.repositories:
                continue
            platform_names = '|'.join(
                platform.name for platform in product.platforms
            )
            platform_pattern = re.compile(
                rf'-({platform_names})-(\w+)(-debug|)-dr$',
                flags=re.IGNORECASE,
            )
            for repo in product.repositories:
                if repo.arch == 'sign_key':
                    continue
                regex_result = platform_pattern.search(repo.name)
                if not regex_result:
                    continue
                platform, *_ = regex_result.groups()
                repo.export_path = f"{product.name}/{platform}/{'debug/' if repo.debug else ''}{repo.arch}/"


if __name__ == '__main__':
    main()

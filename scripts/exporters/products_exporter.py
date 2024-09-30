import argparse
import asyncio
from pathlib import Path
from typing import Literal, List

from sqlalchemy import select
from sqlalchemy.orm import joinedload

from alws.config import settings
from alws.models import Platform, Product, Repository
from alws.utils.fastapi_sqla_setup import setup_all
from alws.dependencies import get_async_db_session
from scripts.exporters.base_exporter import BasePulpExporter


def parse_args():
    parser = argparse.ArgumentParser(
        "product-exporter",
        description=(""),
    )
    parser.add_argument(
        "-p",
        "--product",
        type=str,
        required=True,
        help="",
    )
    parser.add_argument(
        "-d",
        "--distribution",
        type=str,
        required=True,
        help="",
    )
    parser.add_argument(
        "-a",
        "--arches",
        type=str,
        nargs="+",
        required=True,
        help="List of arches to export",
    )
    parser.add_argument(
        "-c",
        "--cache-dir",
        type=str,
        default="~/.cache/pulp_product_exporter",
        required=False,
        help="Repodata cache directory",
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        default=False,
        required=False,
        help="Verbose output",
    )
    parser.add_argument(
        "-method",
        "--export-method",
        type=str,
        default="hardlink",
    )
    return parser.parse_args()


class ProductExporter(BasePulpExporter):
    def __init__(
        self,
        repodata_cache_dir: str,
        logger_name: str = 'product-exporter',
        log_file_path: Path = Path('/tmp/product-exporter.log'),
        verbose: bool = False,
        export_method: Literal['write', 'hardlink', 'symlink'] = 'hardlink',
        export_path: str = settings.pulp_export_path,
    ):
        super().__init__(
            repodata_cache_dir=repodata_cache_dir,
            logger_name=logger_name,
            log_file_path=log_file_path,
            verbose=verbose,
            export_method=export_method,
            export_path=export_path,
        )

    async def export_product_repos(
        self,
        product_name: str,
        distr_name,
        arches: List[str],
    ):
        query = (
            select(Product)
            .where(
                Product.name == product_name,
                Product.platforms.any(Platform.name == distr_name),
                Product.repositories.any(Repository.arch.in_(arches)),
            )
            .options(joinedload(Product.repositories))
        )
        async with get_async_db_session() as session:
            product = (await session.execute(query)).scalars().first()
        return await self.export_repositories(
            list({repo.id for repo in product.repositories})
        )


async def main():
    args = parse_args()
    await setup_all()
    exporter = ProductExporter(
        repodata_cache_dir=args.cache_dir,
        verbose=args.verbose,
        export_method=args.export_method,
    )
    await exporter.export_product_repos(args.product, args.distribution, args.arches)


if __name__ == '__main__':
    asyncio.run(main())

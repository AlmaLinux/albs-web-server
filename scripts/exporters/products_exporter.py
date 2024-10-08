import argparse
import asyncio
import sys
from pathlib import Path
from typing import List, Literal

from sqlalchemy import select
from sqlalchemy.orm import joinedload

sys.path.append(str(Path(__file__).parent.parent.parent))

from alws.config import settings
from alws.dependencies import get_async_db_session
from alws.models import Platform, Product, Repository
from alws.utils.fastapi_sqla_setup import setup_all
from scripts.exporters.base_exporter import BasePulpExporter

SEMAPHORE = asyncio.Semaphore(4)


def parse_args():
    parser = argparse.ArgumentParser(
        "products-exporter",
        description=(
            "Products exporter script. Export product repositories "
            "from Pulp and transfer them to the filesystem"
        ),
    )
    parser.add_argument(
        "-p",
        "--product",
        type=str,
        required=True,
        help="Product name to export",
    )
    parser.add_argument(
        "-d",
        "--distribution",
        type=str,
        required=True,
        help="Distribution name to export",
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
        required=False,
        help="Method of exporting (choices: write, hardlink, symlink)",
    )
    return parser.parse_args()


class ProductExporter(BasePulpExporter):
    def __init__(
        self,
        repodata_cache_dir: str,
        logger_name: str = 'product-exporter',
        log_file_path: Path = Path('/srv/product-exporter.log'),
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
        self.logger.info(
            'Start exporting packages from product: %s',
            product_name,
        )
        query = (
            select(Product)
            .where(
                Product.name == product_name,
                Product.platforms.any(Platform.name == distr_name),
            )
            .options(
                joinedload(
                    Product.repositories.and_(
                        Repository.name.ilike(f'%{distr_name}%'),
                        Repository.arch.in_(arches),
                    )
                )
            )
        )
        async with get_async_db_session() as session:
            product = (await session.execute(query)).scalars().first()
        return await self.export_repositories(
            list({repo.id for repo in product.repositories})
        )


async def repo_post_processing(
    exporter: ProductExporter,
    repo_path: str,
) -> bool:
    async with SEMAPHORE:
        result = False
        try:
            exporter.regenerate_repo_metadata(repo_path)
        except Exception as exc:
            result = False
            exporter.logger.exception("Post-processing failed: %s", str(exc))
        return result


async def main():
    args = parse_args()
    await setup_all()
    exporter = ProductExporter(
        repodata_cache_dir=args.cache_dir,
        verbose=args.verbose,
        export_method=args.export_method,
    )
    exported_paths = await exporter.export_product_repos(
        product_name=args.product,
        distr_name=args.distribution,
        arches=args.arches,
    )
    await asyncio.gather(
        *(repo_post_processing(exporter, path) for path in exported_paths)
    )


if __name__ == '__main__':
    asyncio.run(main())
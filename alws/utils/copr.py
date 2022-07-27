import re
import typing

from alws.config import settings
from alws.models import Product, Repository
from alws.utils.pulp_client import PulpClient

__all__ = [
    'create_product_repo',
    'generate_repo_config',
    'get_platform_name_for_copr_plugin',
    'make_copr_plugin_response',
]


def generate_repo_config(
    repo: Repository,
    ownername: str,
) -> str:
    # we should clean "http" protocol from host url
    clean_host_name = re.sub(r'^(http|https)://', '', settings.pulp_host)
    config_template = (
        f"[copr:{clean_host_name}:{ownername}:{repo.name}]\n"
        f"name=Copr repo for {repo.name} owned by {ownername}\n"
        f"baseurl={re.sub(rf'-{repo.arch}/$', '-$basearch/', repo.url)}\n"
        "type=rpm-md\n"
        "skip_if_unavailable=True\n"
        "gpgcheck=0\n"
        "enabled=1\n"
        "enabled_metadata=1\n"
    )
    return config_template


def make_copr_plugin_response(
    db_products: typing.List[Product],
) -> typing.List[dict]:
    result = []
    for db_product in db_products:
        product_dict = {
            'name': db_product.name,
            'full_name': db_product.full_name,
            'description': db_product.description,
            'ownername': db_product.owner.username,
            'chroot_repos': {
                # we should return repositories
                # by "distr_name-distr_ver-arch" key
                # e.g.: test_user-test_product-epel-8-x86_64 -> "epel-8-x86_64"
                '-'.join(repo.name.split('-')[-3:]): repo.url
                for repo in db_product.repositories
            },
        }
        result.append(product_dict)
    return result


def get_platform_name_for_copr_plugin(platform_name: str) -> str:
    # for "AlmaLinux" distribution dnf COPR plugin use "EPEL" distribution
    if 'almalinux' in platform_name:
        platform_name = platform_name.replace('almalinux', 'epel')
    return platform_name


async def create_product_repo(
    pulp_client: PulpClient,
    product_name: str,
    ownername: str,
    platform_name: str,
    arch: str,
    is_debug: bool,
) -> typing.Tuple[str, str, str, str, bool]:

    debug_suffix = '-debug' if is_debug else ''
    platform_name = get_platform_name_for_copr_plugin(platform_name)
    repo_name = (
        f'{ownername}-{product_name}-{platform_name}-{arch}{debug_suffix}'
    )
    repo_url, repo_href = await pulp_client.create_build_rpm_repo(repo_name)
    return repo_name, repo_url, arch, repo_href, is_debug

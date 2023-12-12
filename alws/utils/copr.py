import re
import typing

from alws.config import settings
from alws.models import Product, Repository
from alws.utils.pulp_client import PulpClient

__all__ = [
    'create_product_repo',
    'create_product_sign_key_repo',
    'generate_repo_config',
    'get_clean_copr_chroot',
    'get_copr_chroot_repo_key',
    'make_copr_plugin_response',
]


def generate_repo_config(
    repo: Repository,
    product_name: str,
    ownername: str,
) -> str:
    # we should clean "http" protocol from host url
    clean_host_name = re.sub(r'^(http|https)://', '', settings.pulp_host)
    repo_url = re.sub('(x86_64|aarch64|ppc64le|i386|i686|s390x)',
                      '$basearch', repo.url)
    repo_url = re.sub('almalinux-(8|9|10)', 'almalinux-$releasever', repo_url)
    config_template = (
        f"[copr:{clean_host_name}:{ownername}:{product_name}]\n"
        f"name=Copr repo for {product_name} {repo.arch} owned by {ownername}\n"
        f"baseurl={repo_url}\n"
        "type=rpm-md\n"
        "skip_if_unavailable=True\n"
        "gpgcheck=0\n"
        "enabled=1\n"
        "enabled_metadata=1\n"
    )
    return config_template


def get_copr_chroot_repo_key(repo_name: str) -> str:
    # we should return repositories by "distr_name-distr_ver-arch" key
    # e.g.: test_user-test_product-AlmaLinux-8-i686-dr -> "epel-8-i686"
    repo_name = repo_name.lower().replace('-almalinux-', '-epel-')
    start_index = -4
    if repo_name.endswith('debug-dr'):
        start_index = -5
    chroot_repo_key = '-'.join(repo_name.split('-')[start_index:-1])
    return chroot_repo_key


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
                get_copr_chroot_repo_key(repo.name): repo.url
                for repo in db_product.repositories
            },
        }
        result.append(product_dict)
    return result


def get_clean_copr_chroot(copr_chroot: str) -> str:
    # for "AlmaLinux" distribution dnf COPR plugin use "EPEL" distribution
    if 'epel' in copr_chroot:
        copr_chroot = copr_chroot.replace('epel', 'almalinux')
    return f"{copr_chroot}-dr"


async def create_product_repo(
    pulp_client: PulpClient,
    product_name: str,
    ownername: str,
    platform_name: str,
    arch: str,
    is_debug: bool,
) -> typing.Tuple[str, str, str, str, bool]:

    debug_suffix = '-debug' if is_debug else ''
    repo_name = (
        f'{ownername}-{product_name}-{platform_name}-{arch}{debug_suffix}-dr'
    )
    repo_url, repo_href = await pulp_client.create_rpm_repository(
        repo_name, auto_publish=False, create_publication=True,
        base_path_start='copr',
    )
    return repo_name, repo_url, arch, repo_href, is_debug


async def create_product_sign_key_repo(
        pulp_client: PulpClient, owner_name: str, product_name: str
) -> typing.Tuple[str, str, str]:
    sign_key_repo_name = f'{owner_name}-{product_name}-sign-key-repo'
    repo_url, repo_href = await pulp_client.create_sign_key_repo(
        sign_key_repo_name)
    return sign_key_repo_name, repo_url, repo_href

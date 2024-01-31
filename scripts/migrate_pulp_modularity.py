import argparse
import asyncio
import logging
import time
import typing
from pathlib import Path

import aiofiles
import requests
import dataclasses
import os
import sys
import yaml

from urllib.parse import urljoin

from aiohttp import ClientResponseError
from hawkey import NEVRA
from requests.auth import HTTPBasicAuth
from sqlalchemy import select

from alws.database import PulpSession
from alws.pulp_models import RpmModulemd, RpmModulemdPackages
from alws.utils.parsing import parse_rpm_nevra
from alws.utils.pulp_client import PulpClient

sys.path.append(os.path.dirname(os.path.dirname(__file__)))


ROOT_FOLDER = '/srv/pulp/media/'


@dataclasses.dataclass(
    frozen=True,
)
class ModuleInfo:
    name: str
    version: int
    stream: str
    arch: str
    context: str

    def __str__(self):
        return (
            f'{self.name}:{self.stream}:{self.version}:'
            f'{self.context}:{self.arch}'
        )

    def __repr__(self):
        return self.__str__()

    def __eq__(self, other):
        return (
            self.name == other.name and
            self.version == other.version and
            self.stream == other.stream and
            self.arch == other.arch and
            self.context == other.context
        )

    @property
    def nsvca(self):
        return f"{self.name}:{self.stream}:{self.version}:{self.context}:{self.arch}"


@dataclasses.dataclass(
    frozen=True,
)
class ModuleFile(ModuleInfo):
    file_content: str
    dependencies: list = dataclasses.field(default_factory=list)
    artifacts: list = dataclasses.field(default_factory=list)
    packages: list = dataclasses.field(default_factory=list)

    def __hash__(self):
        return super().__hash__()

    def __eq__(self, other):
        return super().__eq__(other)

    def __str__(self):
        base = super().__str__()
        return (
            f'{base}\n'
            f'dependencies: {self.dependencies}\n'
            f'artifacts: {self.artifacts}\n'
            f'packages: {self.packages}'
        )


@dataclasses.dataclass
class DefaultModule:
    name: str
    stream: str
    file_content: str
    profiles: list = dataclasses.field(default_factory=list)

    def __str__(self):
        return (
            f'{self.name}:{self.stream}:{self.profiles}:'
        )

    def __repr__(self):
        return self.__str__()

    def __eq__(self, other):
        return (
            self.name == other.name and
            self.stream == other.stream and
            self.profiles == other.profiles
        )

    @property
    def nsvca(self):
        return f"{self.name}:{self.stream}"


async def create_new_module(module_data: ModuleFile, pulp_client: PulpClient):
    try:
        await pulp_client.create_module(
            content=module_data.file_content,
            name=module_data.name,
            stream=module_data.stream,
            context=module_data.context,
            arch=module_data.arch,
            version=module_data.version,
            artifacts=module_data.artifacts,
            dependencies=module_data.dependencies,
            packages=module_data.packages,
        )
    except ClientResponseError:
        logging.info('Module %s already exists', module_data.nsvca)


async def create_new_default_module(module_data: DefaultModule, pulp_client: PulpClient):
    try:
        await pulp_client.create_default_module(
            content=module_data.file_content,
            module=module_data.name,
            stream=module_data.stream,
            profiles=module_data.profiles,
        )
    except ClientResponseError:
        logging.info('Default module %s already exists', module_data.nsvca)


async def get_modules_info(
    pulp_client: PulpClient,
    use_next: bool = True,
    limit: int = 100,
    offset: int = 0,
) -> list[str]:
    result = await pulp_client.get_modules(
        limit=limit,
        offset=offset,
        fields='artifact',
        ordering='-pulp_created',
        use_next=use_next,
    )
    return [i['artifact'] for i in result]


async def get_module_file_path(
    pulp_client: PulpClient,
    uri: str,
) -> str:
    logging.info('Get path by artifact uri: %s', uri)
    result = await pulp_client.get_by_href(uri)
    return result['file']


async def get_module_file_content(
    file_path: str,
    root_folder: str,
):
    path = Path(root_folder).joinpath(file_path)
    if not path.exists():
        logging.warning('Modules.yaml does not exit by path %s', path)
        return []
    async with aiofiles.open(path, mode='r') as fd:
        logging.info('Load modules data by path: %s', path)
        return list(yaml.load_all(await fd.read(), Loader=yaml.CLoader))


async def get_modularity_data(
    pulp_client: PulpClient,
    yaml_content: dict,
    path: str,
) -> typing.Optional[typing.Union[DefaultModule, ModuleFile]]:
    logging.info('Get modularity data by path: %s', path)
    data = yaml_content['data']
    if 'module' in data:
        return DefaultModule(
            name=data['module'],
            stream=next(iter(data['profiles'])),
            file_content=yaml.dump(yaml_content, Dumper=yaml.CDumper),
            profiles=data['profiles'],
        )
    artifacts = data.get('artifacts', {}).get('rpms', [])
    dependencies = [data.get('dependencies', [{}])[0].get('requires', {})]
    return ModuleFile(
        name=data['name'],
        stream=data['stream'],
        version=data['version'],
        arch=data['arch'],
        context=data['context'],
        file_content=yaml.dump(yaml_content, Dumper=yaml.CDumper),
        dependencies=dependencies,
        artifacts=artifacts,
        packages=await get_packages_hrefs_for_module(
            pulp_client=pulp_client,
            artifacts=artifacts,
            path=path,
        )
    )


def extract_nevra_list_of_artifacts(artifacts: list[str]) -> list[NEVRA]:
    return [parse_rpm_nevra(artifact) for artifact in artifacts]


def filter_debug_and_src_artifacts(artifacts: list[NEVRA]) -> list[NEVRA]:
    return [artifact for artifact in artifacts if all([
        artifact.arch != 'src',
        'debug' not in artifact.name,
    ])]


async def get_package_pulp_href_by_params(
    pulp_client: PulpClient,
    arch: str,
    epoch: int,
    name: str,
    release: str,
    version: str,
) -> str:
    result = await pulp_client.get_rpm_packages(
        include_fields=['pulp_href'],
        **{
            'arch': arch,
            'epoch': epoch,
            'name': name,
            'release': release,
            'version': version,
            'ordering': '-pulp_created',
        }
    )
    if result:
        return result[0]['pulp_href']


async def get_packages_hrefs_for_module(
    pulp_client: PulpClient,
    artifacts: list[str],
    path: str,
) -> list[str]:
    logging.info('Get packages hrefs for module by path: %s', path)
    artifacts_nevra = extract_nevra_list_of_artifacts(artifacts)
    filtered_artifacts_nevra = filter_debug_and_src_artifacts(artifacts_nevra)
    return [
        package for artifact_nevra in filtered_artifacts_nevra
        if (package := await get_package_pulp_href_by_params(
            pulp_client=pulp_client,
            arch=artifact_nevra.arch,
            epoch=artifact_nevra.epoch,
            name=artifact_nevra.name,
            release=artifact_nevra.release,
            version=artifact_nevra.version,
        )) is not None
    ]


async def process_module_data(
    pulp_client: PulpClient,
    i: int,
    artifact: str,
    artifacts_len: int,
    root_folder: str,
    dry_run: bool = False,
) -> list[ModuleFile]:
    await asyncio.sleep(1)
    logging.info('Path %s from %s', i + 1, artifacts_len)
    path = await get_module_file_path(pulp_client, artifact)
    yaml_content = await get_module_file_content(
        path,
        root_folder=root_folder,
    )
    total = []
    for content in yaml_content:
        result = await get_modularity_data(
            pulp_client=pulp_client,
            yaml_content=content,
            path=path,
        )
        if isinstance(result, DefaultModule):
            logging.info('Create new default module %s', result.nsvca)
            if not dry_run:
                await create_new_default_module(
                    module_data=result,
                    pulp_client=pulp_client,
                )
        elif isinstance(result, ModuleFile):
            logging.info('Create new module %s', result.nsvca)
            if not dry_run:
                await create_new_module(
                    module_data=result,
                    pulp_client=pulp_client,
                )
            total.append(result)
    return total


def parse_args():
    parser = argparse.ArgumentParser(
        'migrate_pulp_modularity',
        description='The migration script for migrating old '
                    'format modules record to acceptable by Pulp',
    )
    parser.add_argument(
        '-p',
        '--pulp-storage-path',
        type=str,
        required=True,
        help='Path to a directory with filestorage of Pulp. '
             'A directory should contain subdirectory `media`'
    )
    parser.add_argument(
        '-d',
        '--dry-run',
        action='store_true',
        default=False,
        required=False,
        help='Does not actually perform any modifications in Pulp db'
    )
    return parser.parse_args()


async def main():
    args = parse_args()
    logging.basicConfig(
        level=logging.INFO,
        handlers=[
            logging.StreamHandler(),
        ],
    )
    time1 = time.time()
    step = 100
    pulp_host = os.environ["PULP_HOST"]
    pulp_user = os.environ["PULP_USER"]
    pulp_password = os.environ["PULP_PASSWORD"]
    pulp_client = PulpClient(
        pulp_host,
        pulp_user,
        pulp_password,
        asyncio.Semaphore(step),
    )
    artifacts = list(set(await get_modules_info(
        pulp_client=pulp_client,
        use_next=False,
        limit=1000,
        offset=0,
    )))
    migrated_modules = list()
    for i in range(0, len(artifacts), step):
        for j, artifact in enumerate(artifacts[0 + i:i + step]):
            logging.info('Artifact %s by path %s', j + i, artifact)
        migrated_modules.extend(
            result for results in
            await asyncio.gather(*(process_module_data(
                pulp_client,
                j + i,
                artifact,
                len(artifacts),
                args.pulp_storage_path,
                args.dry_run,
            ) for j, artifact in enumerate(artifacts[0+i:i+step])))
            for result in results
        )

    with PulpSession() as pulp_db, pulp_db.begin():
        query = select(RpmModulemd)
        result = pulp_db.execute(query).scalars().all()
        all_modules = {i.nsvca: i for i in result}
        for migrated_module in migrated_modules:
            if migrated_module.nsvca in all_modules:
                del all_modules[migrated_module.nsvca]
        for module in all_modules.values():
            logging.info('Delete old module record %s', module.nsvca)
            modulemd_packages = pulp_db.execute(select(
                RpmModulemdPackages
            ).where(
                RpmModulemdPackages.modulemd_id == module.content_ptr_id)
            ).scalars().all()
            if not args.dry_run:
                for modulemd_package in modulemd_packages:
                    pulp_db.delete(modulemd_package)
                pulp_db.delete(module)
        pulp_db.commit()
    logging.info('Total time: %s', time.time() - time1)


if __name__ == "__main__":
    asyncio.run(main())

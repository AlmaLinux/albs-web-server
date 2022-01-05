import re
import json
import time
import random
import typing
import hashlib
import datetime
import collections

import aiohttp
import yaml
from pydantic import BaseModel
import gi
gi.require_version('Modulemd', '2.0')
from gi.repository import Modulemd


def get_random_unique_version():
    return int(str(int(time.time())) + str(random.randint(1000000, 9999999)))


def calc_dist_macro(
            module_name: str,
            module_stream: str,
            module_version: int,
            module_context: str,
            build_index: int,
            dist_prefix: str
        ) -> str:
    dist_str = '.'.join([
        module_name,
        module_stream,
        str(module_version),
        module_context
    ]).encode('utf-8')
    dist_hash = hashlib.sha1(dist_str).hexdigest()[:8]
    return f'.module_{dist_prefix}+{build_index}+{dist_hash}'


async def get_modified_refs_list(platform_url: str):
    package_list = []
    async with aiohttp.ClientSession() as session:
        async with session.get(platform_url) as response:
            yaml_body = await response.text()
            response.raise_for_status()
            package_list = yaml.safe_load(yaml_body)['modified_packages']
            return package_list


class RpmArtifact(BaseModel):

    name: str
    version: str
    release: str
    epoch: typing.Optional[int]
    arch: str

    def as_artifact(self):
        epoch = self.epoch if self.epoch else '0'
        return f'{self.name}-{epoch}:{self.version}-{self.release}.{self.arch}'

    def as_src_rpm(self):
        return f'{self.name}-{self.version}-{self.release}.src.rpm'

    def as_dict(self):
        return {
            'name': self.name,
            'version': self.version,
            'release': self.release,
            'epoch': self.epoch,
            'arch': self.arch
        }

    @staticmethod
    def from_str(artifact) -> 'RpmArtifact':
        """
        Parse package name/epoch/version/release from package artifact record.

        Parameters
        ----------
        artifact : str
            Stream artifact record.

        Returns
        -------
        RpmArtifact or None
            Parsed package metadata or None.
        """
        regex = re.compile(
            r'^(?P<name>[\w+-.]+)-'
            r'((?P<epoch>\d+):)?'
            r'(?P<version>\d+?[\w.]*)-'
            r'(?P<release>\d+?[\w.+]*?)'
            r'\.(?P<arch>[\w]*)(\.rpm)?$'
        )
        result = re.search(regex, artifact)
        if not result:
            return None
        return RpmArtifact(**result.groupdict())


class ModuleWrapper:

    def __init__(self, index, module, stream):
        self._index = index
        self._module = module
        self._stream = stream

    @classmethod
    def from_template(cls, template: str, name=None, stream=None):
        index = Modulemd.ModuleIndex.new()
        ret, _ = index.update_from_string(template, strict=True)
        if not ret:
            if not all([name, stream]):
                raise ValueError('can not parse modules.yaml template')
            stream = Modulemd.ModuleStreamV2.read_string(
                template, True, name, stream)
            if not stream:
                raise ValueError('can not parse modules.yaml template')
            index.add_module_stream(stream)
        name = index.get_module_names()[0]
        module = index.get_module(name)
        stream = module.get_all_streams()[0]
        return ModuleWrapper(index, module, stream)

    def generate_new_version(self, platform_prefix: str) -> int:
        return int(platform_prefix + datetime.datetime.utcnow().strftime(
            '%Y%m%d%H%M%S'))

    def generate_new_context(self) -> str:
        build_context = self.calc_build_context()
        runtime_context = self.cacl_runtime_context()
        hashes = '{0}:{1}'.format(build_context, runtime_context)
        return hashlib.sha1(hashes.encode('utf-8')).hexdigest()[:8]

    def get_build_deps(self) -> dict:
        build_deps = {}
        # try to extract a detailed requirements list from the
        # xmd['mbs']['buildrequires'] section first
        xmd = self._stream.get_xmd()
        if xmd:
            mbs_build_deps = xmd.get('mbs', {}).get('buildrequires')
            if mbs_build_deps:
                return mbs_build_deps
        # convert dependencies['buildrequires'] to the xmd-like format
        for deps in self._stream.get_dependencies():
            for name in deps.get_buildtime_modules():
                streams = deps.get_buildtime_streams(name)
                if streams:
                    build_deps[name] = {'stream': streams[0]}
        return build_deps

    def get_runtime_deps(self) -> dict:
        requires = {}
        for deps in self._stream.get_dependencies():
            for name in deps.get_runtime_modules():
                streams = deps.get_runtime_streams(name)
                requires[name] = requires.get(name, set()).union(streams)
        return {
            name: sorted(list(streams))
            for name, streams in requires.items()
        }

    def calc_build_context(self):
        build_deps = self.get_build_deps()
        requires = {name: info['stream'] for name, info in build_deps.items()}
        js = json.dumps(collections.OrderedDict(sorted(requires.items())))
        return hashlib.sha1(js.encode('utf-8')).hexdigest()

    def cacl_runtime_context(self):
        runtime_deps = self.get_runtime_deps()
        requires = {dep: sorted(list(streams))
                    for dep, streams in runtime_deps.items()}
        js = json.dumps(collections.OrderedDict(sorted(requires.items())))
        return hashlib.sha1(js.encode('utf-8')).hexdigest()

    def set_arch_list(self, arch_list: typing.List[str]):
        for component_name in self._stream.get_rpm_component_names():
            component = self._stream.get_rpm_component(component_name)
            component.reset_arches()
            for arch in arch_list:
                component.add_restricted_arch(arch)

    def add_rpm_artifact(self, rpm_pkg: dict):
        artifact = RpmArtifact(
            name=rpm_pkg['name'],
            epoch=int(rpm_pkg['epoch']),
            version=rpm_pkg['version'],
            release=rpm_pkg['release'],
            arch=rpm_pkg['arch']
        ).as_artifact()
        if not self.is_artifact_filtered(artifact):
            self._stream.add_rpm_artifact(artifact)

    def is_artifact_filtered(self, artifact: str) -> bool:
        for filter_name in self._stream.get_rpm_filters():
            if artifact.startswith(filter_name):
                return True
        return False

    def iter_components(self):
        components = [
            (component_name, self._stream.get_rpm_component(component_name))
            for component_name in self._stream.get_rpm_component_names()
        ]
        yield from sorted(components, key=lambda i: i[1].get_buildorder())

    def set_component_ref(self, component_name, ref):
        component = self._stream.get_rpm_component(component_name)
        component.set_ref(ref)

    def iter_mock_definitions(self):
        buildopts = self._stream.get_buildopts()
        if buildopts is None:
            return
        macros_template = buildopts.get_rpm_macros() or ''
        for macros in macros_template.splitlines():
            macros = macros.strip()
            if not macros or macros.startswith('#'):
                continue
            name, *value = macros.split()
            # erasing %...
            name = name[1:]
            value = ' '.join(value)
            yield name, value

    def iter_dependencies(self):
        for dep in self._stream.get_dependencies():
            for module in dep.get_buildtime_modules():
                if module == 'platform':
                    continue
                if module == self.name:
                    continue
                for stream in dep.get_buildtime_streams(module):
                    yield module, stream

    def render(self) -> str:
        return self._index.dump_to_string()

    @property
    def name(self) -> str:
        return self._stream.get_module_name()

    @property
    def stream(self) -> str:
        return self._stream.get_stream_name()

    @property
    def version(self) -> int:
        return self._stream.get_version()

    @version.setter
    def version(self, version: int):
        self._stream.set_version(version)

    @property
    def context(self) -> str:
        return self._stream.get_context()

    @context.setter
    def context(self, context: str):
        self._stream.set_context(context)

    @property
    def arch(self) -> str:
        return self._stream.get_arch()

    @arch.setter
    def arch(self, arch: str):
        self._stream.set_arch(arch)

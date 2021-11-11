import json
import time
import random
import typing
import hashlib
import datetime
import collections

import yaml
import pydantic


def get_random_unique_version():
    return int(str(int(time.time())) + str(random.randint(1000000, 9999999)))


class ModuleRpmComponent(pydantic.BaseModel):

    name: str
    ref: str
    rationale: str
    buildorder: int


class ModuleWrapper(pydantic.BaseModel):

    name: str
    stream: str
    version: typing.Optional[str]
    context: typing.Optional[str]
    arch: typing.Optional[str]
    artifacts: typing.List = []
    data: dict

    @classmethod
    def from_template(cls, template: str):
        data = yaml.safe_load(template)['data']
        stream = data.pop('stream')
        name = data.pop('name')
        version = data.pop('version', None)
        context = data.pop('context', None)
        arch = data.pop('arch', None)
        artifacts = data.pop('artifacts', {}).get('rpms', [])
        return cls(
            name=name,
            stream=stream,
            version=version,
            context=context,
            arch=arch,
            artifacts=artifacts,
            data=data
        )

    def generate_new_version(self) -> str:
        # TODO: instead of 80100 should be platform prefix
        return '80100' + datetime.datetime.utcnow().strftime(
            '%Y%m%d%H%M%S')

    def generate_new_context(self) -> str:
        build_context = self.calc_build_context()
        runtime_context = self.cacl_runtime_context()
        hashes = '{0}:{1}'.format(build_context, runtime_context)
        return hashlib.sha1(hashes.encode('utf-8')).hexdigest()[:8]

    def get_build_deps(self) -> dict:
        build_deps = {}
        # try to extract a detailed requirements list from the
        # xmd['mbs']['buildrequires'] section first
        xmd = self.data.get('xmd')
        if xmd:
            build_deps = xmd.get('mbs', {}).get('buildrequires')
            if build_deps:
                return build_deps
        # convert dependencies['buildrequires'] to the xmd-like format
        build_requires = self.data['dependencies']
        for deps in build_requires:
            for name, streams in deps.get('buildrequires', {}).items():
                if len(streams) > 1:
                    raise ValueError(
                        'multiple stream versions are not supported')
                if streams:
                    build_deps[name] = {'stream': streams[0]}
        return build_deps

    def get_runtime_deps(self) -> dict:
        requires = {}
        dependencies = self.data['dependencies']
        for deps in dependencies:
            for name, streams in deps.get('requires', {}).items():
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

    def calc_dist_macro(self, build_index: int, dist_prefix: str) -> str:
        dist_str = '.'.join([
            self.name,
            self.stream,
            str(self.version),
            str(self.context)
        ]).encode('utf-8')
        dist_hash = hashlib.sha1(dist_str).hexdigest()[:8]
        return f'.module_{dist_prefix}+{build_index}+{dist_hash}'

    def set_arch_list(self, arch_list: typing.List[str]):
        for v in self.data['components']['rpms'].values():
            v['arches'] = arch_list[:]

    def add_rpm_artifact(self, artifact: str):
        if not self.is_artifact_filtered(artifact):
            self.artifacts.append(artifact)

    def is_artifact_filtered(self, artifact: str) -> bool:
        for filter_name in self.data.get('filter', {}).get('rpms', []):
            if artifact.startswith(filter_name):
                return True
        return False

    def iter_components(self):
        components = [
            ModuleRpmComponent(name=k, **v)
            for k, v in self.data['components']['rpms'].items()
        ]
        yield from sorted(components, key=lambda i: i.buildorder)

    def render(self) -> str:
        data = self.dict()
        data.update(data.pop('data'))
        data['artifacts'] = {'rpms': data.pop('artifacts')}
        return yaml.safe_dump({'data': data})

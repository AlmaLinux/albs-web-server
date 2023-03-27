import collections
import datetime
import hashlib
import json
import logging
import re
import typing
import urllib.parse

import aiohttp
import gi
import requests
import yaml
from pydantic import BaseModel

gi.require_version("Modulemd", "2.0")
from gi.repository import Modulemd


def calc_dist_macro(
    module_name: str,
    module_stream: str,
    module_version: int,
    module_context: str,
    build_index: int,
    dist_prefix: str,
) -> str:
    dist_str = ".".join(
        [module_name, module_stream, str(module_version), module_context]
    ).encode("utf-8")
    dist_hash = hashlib.sha1(dist_str).hexdigest()[:8]
    return f".module_{dist_prefix}+{build_index}+{dist_hash}"


async def get_modified_refs_list(platform_url: str):
    package_list = []
    async with aiohttp.ClientSession() as session:
        async with session.get(platform_url) as response:
            yaml_body = await response.text()
            response.raise_for_status()
            package_list = yaml.safe_load(yaml_body)["modified_packages"]
            return package_list


def get_modules_yaml_from_repo(repo_name: str):
    base_url = "https://build.almalinux.org/pulp/content/prod/"
    repo_url = urllib.parse.urljoin(base_url, f"{repo_name}/repodata/")
    response = requests.get(repo_url)
    try:
        response.raise_for_status()
    except Exception as exc:
        raise (exc)
    template_href = next(
        (
            line.strip()
            for line in response.text.splitlines()
            if line and "modules" in line
        ),
        None,
    )
    if not template_href:
        return
    template_href = re.search(
        r'href="(.+-modules.yaml)"',
        template_href,
    ).group(1)
    response = requests.get(urllib.parse.urljoin(repo_url, template_href))
    response.raise_for_status()
    return response.text


class RpmArtifact(BaseModel):
    name: str
    version: str
    release: str
    epoch: typing.Optional[int]
    arch: str

    def __hash__(self):
        return hash(self.as_artifact())

    def as_artifact(self):
        epoch = self.epoch if self.epoch else "0"
        return f"{self.name}-{epoch}:{self.version}-{self.release}.{self.arch}"

    def as_src_rpm(self):
        return f"{self.name}-{self.version}-{self.release}.src.rpm"

    def as_dict(self):
        return {
            "name": self.name,
            "version": self.version,
            "release": self.release,
            "epoch": self.epoch,
            "arch": self.arch,
        }

    @staticmethod
    def from_str(artifact) -> "RpmArtifact":
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
            r"^(?P<name>[\w+-.]+)-"
            r"((?P<epoch>\d+):)?"
            r"(?P<version>\d+?[\w.]*)-"
            r"(?P<release>\d+?[\w.+]*?)"
            r"\.(?P<arch>[\w]*)(\.rpm)?$"
        )
        result = re.search(regex, artifact)
        if not result:
            return
        return RpmArtifact(**result.groupdict())

    @staticmethod
    def from_pulp_model(rpm_pkg: dict) -> "RpmArtifact":
        return RpmArtifact(
            name=rpm_pkg["name"],
            epoch=int(rpm_pkg["epoch"]),
            version=rpm_pkg["version"],
            release=rpm_pkg["release"],
            arch=rpm_pkg["arch"],
        )


class ModuleWrapper:
    def __init__(self, stream):
        self._stream = stream

    @classmethod
    def from_template(cls, template: str, name=None, stream=None):
        if all([name, stream]):
            md_stream = Modulemd.read_packager_string(
                template,
                name,
                stream,
            )
        else:
            md_stream = Modulemd.read_packager_string(template)
        if not md_stream:
            raise ValueError("can not parse modules.yaml template")
        return ModuleWrapper(md_stream)

    @staticmethod
    def generate_new_version(platform_prefix: str) -> int:
        return int(
            platform_prefix
            + datetime.datetime.utcnow().strftime("%Y%m%d%H%M%S")
        )

    def generate_new_context(self) -> str:
        build_context = self.calc_build_context()
        runtime_context = self.cacl_runtime_context()
        hashes = "{0}:{1}".format(build_context, runtime_context)
        return hashlib.sha1(hashes.encode("utf-8")).hexdigest()[:8]

    def get_name_and_stream(self, module) -> typing.Tuple[str, str]:
        if not ":" in module:
            return module, ""
        module_dep = module.split(":")
        if len(module_dep) != 2:
            logging.error(
                "Incorrect build-time dependency definition: %s", module
            )
            return
        module_name, module_stream = module_dep
        return module_name, module_stream

    # Add stream to dependency from frontend
    def add_module_dependencies_from_mock_defs(self, enabled_modules: dict):
        old_deps = Modulemd.Dependencies()
        new_deps = Modulemd.Dependencies()
        new_buildtime_modules = []
        new_runtime_modules = []
        if enabled_modules:
            for module in enabled_modules["buildtime"]:
                new_buildtime_modules.append(self.get_name_and_stream(module))
            for module in enabled_modules["runtime"]:
                new_runtime_modules.append(self.get_name_and_stream(module))

        if self._stream.get_dependencies():
            old_deps = self._stream.get_dependencies()[0]
            old_buildtime = old_deps.get_buildtime_modules()
            old_runtime = old_deps.get_runtime_modules()

        # Override build time modules
        if new_buildtime_modules:
            for name, stream in new_buildtime_modules:
                if name in old_buildtime:
                    if stream:
                        new_deps.add_buildtime_stream(name, stream)
                    else:
                        new_deps.set_empty_buildtime_dependencies_for_module(
                            name
                        )

        for module in old_buildtime:
            if module == "platform":
                for stream in old_deps.get_buildtime_streams(module):
                    new_deps.add_buildtime_stream(module, stream)

        # Override runtime modules
        if new_runtime_modules:
            for name, stream in new_runtime_modules:
                if name in old_runtime:
                    if stream:
                        new_deps.add_runtime_stream(name, stream)
                    else:
                        new_deps.set_empty_runtime_dependencies_for_module(
                            name
                        )

        for module in old_runtime:
            if module == "platform":
                for stream in old_deps.get_runtime_streams(module):
                    new_deps.add_runtime_stream(module, stream)

        self._stream.clear_dependencies()
        self._stream.add_dependencies(new_deps)

    def add_module_dependency_to_devel_module(self, module):
        deps = self._stream.get_dependencies()[0]
        deps.add_runtime_stream(module.name, module.stream)
        self._stream.clear_dependencies()
        self._stream.add_dependencies(deps)

    def get_build_deps(self) -> dict:
        build_deps = {}
        # try to extract a detailed requirements list from the
        # xmd['mbs']['buildrequires'] section first
        xmd = self._stream.get_xmd()
        if xmd:
            mbs_build_deps = xmd.get("mbs", {}).get("buildrequires")
            if mbs_build_deps:
                return mbs_build_deps
        # convert dependencies['buildrequires'] to the xmd-like format
        for deps in self._stream.get_dependencies():
            for name in deps.get_buildtime_modules():
                streams = deps.get_buildtime_streams(name)
                if streams:
                    build_deps[name] = {"stream": streams[0]}
        return build_deps

    def get_runtime_deps(self) -> dict:
        requires = {}
        for deps in self._stream.get_dependencies():
            for name in deps.get_runtime_modules():
                streams = deps.get_runtime_streams(name)
                requires[name] = requires.get(name, set()).union(streams)
        return {
            name: sorted(list(streams)) for name, streams in requires.items()
        }

    def calc_build_context(self):
        build_deps = self.get_build_deps()
        requires = {name: info["stream"] for name, info in build_deps.items()}
        js = json.dumps(collections.OrderedDict(sorted(requires.items())))
        return hashlib.sha1(js.encode("utf-8")).hexdigest()

    def cacl_runtime_context(self):
        runtime_deps = self.get_runtime_deps()
        requires = {
            dep: sorted(list(streams)) for dep, streams in runtime_deps.items()
        }
        js = json.dumps(collections.OrderedDict(sorted(requires.items())))
        return hashlib.sha1(js.encode("utf-8")).hexdigest()

    def set_arch_list(self, arch_list: typing.List[str]):
        for component_name in self._stream.get_rpm_component_names():
            component = self._stream.get_rpm_component(component_name)
            component.clear_arches()
            for arch in arch_list:
                component.add_restricted_arch(arch)

    def add_rpm_artifact(
        self,
        rpm_pkg: dict,
        devel: bool = False,
        multilib: bool = False,
    ) -> bool:
        artifact = RpmArtifact.from_pulp_model(rpm_pkg).as_artifact()
        module_is_devel = self.is_devel

        if multilib:
            self._stream.add_rpm_artifact(artifact)
            return True

        if devel and module_is_devel:
            self._stream.add_rpm_artifact(artifact)
            return True

        if self.is_artifact_filtered(rpm_pkg):
            if module_is_devel or rpm_pkg["arch"] == "src":
                self._stream.add_rpm_artifact(artifact)
                return True
        else:
            if not module_is_devel:
                self._stream.add_rpm_artifact(artifact)
                return True

        return False

    def remove_rpm_artifact(self, artifact: str):
        self._stream.remove_rpm_artifact(artifact)

    def remove_rpm_artifacts(self):
        self._stream.clear_rpm_artifacts()

    def is_artifact_filtered(self, artifact: dict) -> bool:
        for filter_name in self._stream.get_rpm_filters():
            if artifact["name"] == filter_name:
                return True
        return False

    def get_rpm_artifacts(self) -> typing.List[str]:
        return self._stream.get_rpm_artifacts()

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
        macros_template = buildopts.get_rpm_macros() or ""
        for macros in macros_template.splitlines():
            macros = macros.strip()
            if not macros or macros.startswith("#"):
                continue
            name, *value = macros.split()
            # erasing %...
            name = name[1:]
            value = " ".join(value)
            yield name, value

    def iter_dependencies(self):
        for dep in self._stream.get_dependencies():
            for module in dep.get_buildtime_modules():
                if module == "platform":
                    continue
                if module == self.name:
                    continue
                for stream in dep.get_buildtime_streams(module):
                    yield module, stream

    # Returns all module build and runtime dependencies with/without stream
    def get_all_build_deps(self):
        deps = {"buildtime": [], "runtime": []}
        for dep in self._stream.get_dependencies():
            for module in dep.get_buildtime_modules():
                if module == "platform":
                    continue
                if module == self.name:
                    continue
                streams = dep.get_buildtime_streams(module)
                if not streams:
                    deps["buildtime"].append(f"{module}:")
                    continue
                for stream in streams:
                    deps["buildtime"].append(f"{module}:{stream}")
            for module in dep.get_runtime_modules():
                if module == "platform":
                    continue
                if module == self.name:
                    continue
                streams = dep.get_runtime_streams(module)
                if not streams:
                    deps["runtime"].append(f"{module}:")
                    continue
                for stream in streams:
                    deps["runtime"].append(f"{module}:{stream}")
        return deps

    @property
    def nsvca(self) -> str:
        return (
            f"{self.name}:{self.stream}:{self.version}:"
            f"{self.context}:{self.arch}"
        )

    def render(self) -> str:
        index = IndexWrapper()
        index.add_module(self)
        return index.render()

    @property
    def name(self) -> str:
        return self._stream.get_module_name()

    @property
    def is_devel(self) -> bool:
        return self.name.endswith("-devel")

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


class IndexWrapper:
    def __init__(self, index=None):
        if index is None:
            index = Modulemd.ModuleIndex.new()
        self._index = index

    @staticmethod
    def from_template(template: str):
        index = Modulemd.ModuleIndex.new()
        ret, error = index.update_from_string(template, strict=True)
        if not ret:
            raise ValueError(
                f"Can not parse modules.yaml template, "
                f"error: {error[0].get_gerror()}"
            )
        return IndexWrapper(index)

    def get_module(self, name: str, stream: str) -> ModuleWrapper:
        module = self._index.get_module(name)
        if not module:
            raise ModuleNotFoundError(f"Index doesn't contain {name}:{stream}")
        for module_stream in module.get_all_streams():
            if module_stream.get_stream_name() == stream:
                return ModuleWrapper(module_stream)
        raise ModuleNotFoundError(f"Index doesn't contain {name}:{stream}")

    def add_module(self, module: ModuleWrapper):
        self._index.add_module_stream(module._stream)

    def has_devel_module(self):
        for module_name in self._index.get_module_names():
            if "-devel" in module_name:
                return True
        return False

    def iter_modules(self):
        for module_name in self._index.get_module_names():
            module = self._index.get_module(module_name)
            for stream in module.get_all_streams():
                yield ModuleWrapper(stream)

    def render(self) -> str:
        return self._index.dump_to_string()

    def copy(self):
        return self.from_template(self.render())

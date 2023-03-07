from alws.utils.modularity import ModuleWrapper, IndexWrapper
from alws.utils.parsing import parse_rpm_nevra


def test_add_rpm_artifact(
    modules_yaml_with_filter: bytes,
):
    module_index = IndexWrapper.from_template(
        modules_yaml_with_filter.decode()
    )

    module_index_with_artifacts = IndexWrapper.from_template(
        modules_yaml_with_filter.decode()
    )
    all_artifacts = []
    for _module in module_index_with_artifacts.iter_modules():
        all_artifacts += _module.get_rpm_artifacts()

    for _module in module_index.iter_modules():
        _module.remove_rpm_artifacts()
        for artifact in all_artifacts:
            pkg_nevra = parse_rpm_nevra(artifact)
            pkg = {
                "name": pkg_nevra.name,
                "epoch": pkg_nevra.epoch,
                "version": pkg_nevra.version,
                "release": pkg_nevra.release,
                "arch": pkg_nevra.arch
            }
            _module.add_rpm_artifact(pkg)
        module_with_artifacts = module_index_with_artifacts.get_module(
            name=_module.name,
            stream=_module.stream
        )
        artifacts = module_with_artifacts.get_rpm_artifacts()

        new_artifacts = _module.get_rpm_artifacts()

        assert new_artifacts == artifacts

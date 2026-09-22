import copy

from scripts.upload_repository_metadata import (
    ModuleKey,
    StreamKey,
    collect_modules,
    compare_modules,
    group_by_stream,
)

PERL_DBI = StreamKey('perl-DBI', '1.641', '8100020260921064825')


def test_collect_modules_keeps_every_context(
    modules_yaml_multiple_contexts: bytes,
):
    modules = collect_modules(modules_yaml_multiple_contexts.decode())
    assert len(modules) == 4
    stats = group_by_stream(modules)
    # one name:stream:version holding 4 modules that only differ in
    # their dependencies and, therefore, in their contexts
    assert list(stats) == [PERL_DBI]
    assert stats[PERL_DBI].modules == 4
    assert stats[PERL_DBI].contexts == {
        '082fdf2f',
        '0ccef39c',
        'dbc5bc9a',
        'fbe42456',
    }
    assert stats[PERL_DBI].arches == {'x86_64'}
    assert stats[PERL_DBI].artifacts == 16
    assert all(len(info.artifacts) == 4 for info in modules.values())
    assert sorted(
        info.runtime_deps['perl'][0] for info in modules.values()
    ) == ['5.24', '5.26', '5.30', '5.32']


def test_compare_modules_with_identical_metadata(
    modules_yaml_multiple_contexts: bytes,
):
    template = modules_yaml_multiple_contexts.decode()
    uploaded = collect_modules(template)
    published = collect_modules(template)
    assert compare_modules(uploaded, published) == []


def test_compare_modules_reports_lost_context(
    modules_yaml_multiple_contexts: bytes,
):
    uploaded = collect_modules(modules_yaml_multiple_contexts.decode())
    published = dict(uploaded)
    lost = ModuleKey(*PERL_DBI, '082fdf2f', 'x86_64')
    del published[lost]

    problems = compare_modules(uploaded, published)
    assert f'{PERL_DBI}: uploaded 4 module(s), published 3' in problems
    assert f'{lost}: missing in published metadata' in problems
    assert any('contexts differ' in problem for problem in problems)


def test_compare_modules_reports_unexpected_module(
    modules_yaml_multiple_contexts: bytes,
):
    uploaded = collect_modules(modules_yaml_multiple_contexts.decode())
    published = copy.deepcopy(uploaded)
    unexpected = ModuleKey(*PERL_DBI, 'deadbeef', 'x86_64')
    published[unexpected] = copy.deepcopy(next(iter(uploaded.values())))

    problems = compare_modules(uploaded, published)
    assert f'{PERL_DBI}: uploaded 4 module(s), published 5' in problems
    assert f'{unexpected}: unexpected in published metadata' in problems


def test_compare_modules_reports_artifacts_difference(
    modules_yaml_multiple_contexts: bytes,
):
    uploaded = collect_modules(modules_yaml_multiple_contexts.decode())
    published = copy.deepcopy(uploaded)
    key = ModuleKey(*PERL_DBI, '082fdf2f', 'x86_64')
    dropped = sorted(published[key].artifacts)[0]
    published[key].artifacts.remove(dropped)
    published[key].artifacts.add('perl-DBI-0:1.641-10.module_el8.noarch')

    problems = compare_modules(uploaded, published)
    assert (
        f'{key}: artifacts differ, uploaded 4, published 4, '
        f'missing 1, unexpected 1' in problems
    )
    assert (
        f'{key}: artifacts missing in published metadata: {dropped}' in problems
    )
    assert (
        f'{key}: unexpected artifacts in published metadata: '
        f'perl-DBI-0:1.641-10.module_el8.noarch' in problems
    )


def test_compare_modules_reports_runtime_deps_difference(
    modules_yaml_multiple_contexts: bytes,
):
    uploaded = collect_modules(modules_yaml_multiple_contexts.decode())
    published = copy.deepcopy(uploaded)
    key = ModuleKey(*PERL_DBI, '082fdf2f', 'x86_64')
    published[key].runtime_deps = {'platform': ['el9']}

    problems = compare_modules(uploaded, published)
    assert (
        f'{key}: runtime dependencies differ, '
        f'uploaded [perl:[5.24], platform:[el8]], '
        f'published [platform:[el9]]' in problems
    )

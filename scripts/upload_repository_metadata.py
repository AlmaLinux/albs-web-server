import asyncio
import logging
import os.path
import sys
from argparse import ArgumentParser
from collections import defaultdict
from dataclasses import dataclass, field
from io import BytesIO
from typing import Dict, List, NamedTuple, Optional, Set, Tuple

from fastapi import UploadFile
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from alws import models
from alws.dependencies import get_async_db_session
from alws.utils.fastapi_sqla_setup import setup_all
from alws.utils.modularity import IndexWrapper
from alws.utils.pulp_client import PulpClient
from alws.utils.uploader import MetadataUploader

EXIT_OK = 0
EXIT_ERROR = 1
EXIT_POST_CHECK_FAILED = 2

# How many entries a single post-check difference reports before it gets
# truncated. --verbose lifts the limit.
MAX_REPORTED_ITEMS = 10

logger = logging.getLogger('metadata-uploader')


class ModuleKey(NamedTuple):
    """Full module stream identity, i.e. its NSVCA."""

    name: str
    stream: str
    version: str
    context: str
    arch: str

    def __str__(self) -> str:
        return ':'.join(self)

    @property
    def stream_key(self) -> 'StreamKey':
        return StreamKey(self.name, self.stream, self.version)


class StreamKey(NamedTuple):
    """Module stream identity without the context and the arch."""

    name: str
    stream: str
    version: str

    def __str__(self) -> str:
        return ':'.join(self)


@dataclass
class ModuleInfo:
    """Payload of a single module stream the post-check compares."""

    artifacts: Set[str] = field(default_factory=set)
    runtime_deps: Dict[str, List[str]] = field(default_factory=dict)


@dataclass
class StreamStats:
    """Counters aggregated over every module sharing a StreamKey.

    A single name:stream:version is usually present several times:
    perl-DBI:1.641 ships as 4 modules of the very same version that differ
    only in their dependencies and, therefore, in their contexts.
    """

    modules: int = 0
    contexts: Set[str] = field(default_factory=set)
    arches: Set[str] = field(default_factory=set)
    artifacts: int = 0


def collect_modules(template: str) -> Dict[ModuleKey, ModuleInfo]:
    """Index every module stream of a modules.yaml by its NSVCA."""
    modules: Dict[ModuleKey, ModuleInfo] = {}
    index = IndexWrapper.from_template(template)
    for module in index.iter_modules():
        key = ModuleKey(
            name=module.name or '',
            stream=module.stream or '',
            version=str(module.version),
            context=module.context or '',
            arch=module.arch or '',
        )
        artifacts = set(module.get_rpm_artifacts())
        if key in modules:
            # NSVCA is unique within an index, so this should never happen
            logger.warning('Duplicated module in metadata: %s', key)
            modules[key].artifacts.update(artifacts)
            continue
        modules[key] = ModuleInfo(
            artifacts=artifacts,
            runtime_deps=module.get_runtime_deps(),
        )
    return modules


def group_by_stream(
    modules: Dict[ModuleKey, ModuleInfo],
) -> Dict[StreamKey, StreamStats]:
    stats: Dict[StreamKey, StreamStats] = defaultdict(StreamStats)
    for key, info in modules.items():
        entry = stats[key.stream_key]
        entry.modules += 1
        entry.contexts.add(key.context)
        entry.arches.add(key.arch)
        entry.artifacts += len(info.artifacts)
    return dict(stats)


def format_items(items, verbose: bool = False) -> str:
    items = sorted(str(item) for item in items)
    hidden = len(items) - MAX_REPORTED_ITEMS
    if not verbose and hidden > 0:
        items = items[:MAX_REPORTED_ITEMS]
        return f'{", ".join(items)} and {hidden} more'
    return ', '.join(items)


def format_deps(deps: Dict[str, List[str]]) -> str:
    return ', '.join(
        f'{name}:[{",".join(sorted(streams))}]'
        for name, streams in sorted(deps.items())
    )


def format_stats(stats: StreamStats) -> str:
    return (
        f'modules={stats.modules} contexts={len(stats.contexts)} '
        f'artifacts={stats.artifacts}'
    )


def log_modules_summary(
    uploaded: Dict[ModuleKey, ModuleInfo],
    published: Dict[ModuleKey, ModuleInfo],
    verbose: bool = False,
) -> None:
    """Report how many modules and artifacts both sides hold.

    Every name:stream:version gets its own line, so a module shipped as
    several contexts of the same version is counted as such. Matching
    lines are only logged with --verbose, mismatching ones always are.
    """
    uploaded_stats = group_by_stream(uploaded)
    published_stats = group_by_stream(published)
    logger.info(
        'Modules: uploaded %d, published %d. '
        'Artifacts: uploaded %d, published %d',
        len(uploaded),
        len(published),
        sum(len(info.artifacts) for info in uploaded.values()),
        sum(len(info.artifacts) for info in published.values()),
    )
    matched = 0
    for stream_key in sorted(set(uploaded_stats) | set(published_stats)):
        uploaded_entry = uploaded_stats.get(stream_key, StreamStats())
        published_entry = published_stats.get(stream_key, StreamStats())
        if uploaded_entry == published_entry:
            matched += 1
            if not verbose:
                continue
        logger.info(
            '  %-55s uploaded: %s | published: %s | %s',
            stream_key,
            format_stats(uploaded_entry),
            format_stats(published_entry),
            'OK' if uploaded_entry == published_entry else 'MISMATCH',
        )
    if matched and not verbose:
        logger.info(
            '  %d name:stream:version group(s) match, '
            'pass --verbose to list them',
            matched,
        )


def compare_module(
    key: ModuleKey,
    uploaded: ModuleInfo,
    published: ModuleInfo,
    verbose: bool = False,
) -> List[str]:
    problems = []
    missing = uploaded.artifacts - published.artifacts
    unexpected = published.artifacts - uploaded.artifacts
    if missing or unexpected:
        problems.append(
            f'{key}: artifacts differ, uploaded {len(uploaded.artifacts)}, '
            f'published {len(published.artifacts)}, '
            f'missing {len(missing)}, unexpected {len(unexpected)}'
        )
    if missing:
        problems.append(
            f'{key}: artifacts missing in published metadata: '
            f'{format_items(missing, verbose)}'
        )
    if unexpected:
        problems.append(
            f'{key}: unexpected artifacts in published metadata: '
            f'{format_items(unexpected, verbose)}'
        )
    if uploaded.runtime_deps != published.runtime_deps:
        problems.append(
            f'{key}: runtime dependencies differ, '
            f'uploaded [{format_deps(uploaded.runtime_deps)}], '
            f'published [{format_deps(published.runtime_deps)}]'
        )
    return problems


def compare_modules(
    uploaded: Dict[ModuleKey, ModuleInfo],
    published: Dict[ModuleKey, ModuleInfo],
    verbose: bool = False,
) -> List[str]:
    """List every difference between the uploaded and published metadata."""
    problems = []
    uploaded_stats = group_by_stream(uploaded)
    published_stats = group_by_stream(published)
    for stream_key in sorted(set(uploaded_stats) | set(published_stats)):
        uploaded_entry = uploaded_stats.get(stream_key, StreamStats())
        published_entry = published_stats.get(stream_key, StreamStats())
        if uploaded_entry.modules != published_entry.modules:
            problems.append(
                f'{stream_key}: uploaded {uploaded_entry.modules} '
                f'module(s), published {published_entry.modules}'
            )
        for attribute in ('contexts', 'arches'):
            uploaded_values = getattr(uploaded_entry, attribute)
            published_values = getattr(published_entry, attribute)
            if uploaded_values == published_values:
                continue
            problems.append(
                f'{stream_key}: {attribute} differ, uploaded '
                f'[{format_items(uploaded_values, verbose)}], published '
                f'[{format_items(published_values, verbose)}]'
            )
    for key in sorted(set(uploaded) - set(published)):
        problems.append(f'{key}: missing in published metadata')
    for key in sorted(set(published) - set(uploaded)):
        problems.append(f'{key}: unexpected in published metadata')
    for key in sorted(set(uploaded) & set(published)):
        problems.extend(
            compare_module(key, uploaded[key], published[key], verbose)
        )
    return problems


async def get_repo_base_url(
    pulp: PulpClient,
    repo: dict,
    session: AsyncSession,
) -> Optional[str]:
    """Find the URL the repository content is served from."""
    repo_href = repo['pulp_href']
    repo_name = repo['name']
    distros = await pulp.get_rpm_distros(name__contains=repo_name)
    for distro in distros:
        if distro.get('repository') == repo_href:
            return distro['base_url']
    for distro in distros:
        if distro.get('name') in (f'{repo_name}-distro', repo_name):
            return distro['base_url']
    db_repo = (
        (
            await session.execute(
                select(models.Repository).where(
                    models.Repository.pulp_href == repo_href
                )
            )
        )
        .scalars()
        .first()
    )
    return db_repo.url if db_repo else None


async def fetch_published_modules(
    pulp: PulpClient,
    base_url: str,
) -> Tuple[Optional[Dict[ModuleKey, ModuleInfo]], Optional[str]]:
    """Download and parse the modules.yaml the repository publishes."""
    if not base_url.endswith('/'):
        base_url += '/'
    try:
        content = await pulp.get_repo_modules_yaml(base_url)
    except Exception as exc:
        return None, f'cannot download published modules.yaml: {exc}'
    if not content:
        return None, 'published repository has no modules.yaml'
    try:
        return collect_modules(content), None
    except Exception as exc:
        return None, f'cannot parse published modules.yaml: {exc}'


async def post_check_modules(
    uploader: MetadataUploader,
    session: AsyncSession,
    module_content: str,
    retries: int = 3,
    delay: float = 15.0,
    verbose: bool = False,
) -> bool:
    """Download the published modules.yaml back and compare it with ours.

    Pulp rebuilds modules.yaml out of the snippets it stores, so the
    published metadata is not guaranteed to repeat the uploaded one: the
    check compares module names, versions, contexts, arches, runtime
    dependencies and the artifacts list of every module.
    """
    uploaded = collect_modules(module_content)
    repo = await uploader.pulp.get_rpm_repository_by_params(
        {'name': uploader.repo_name},
    )
    if not repo:
        logger.error(
            'Post-check failed: repository %s not found', uploader.repo_name
        )
        return False
    base_url = await get_repo_base_url(uploader.pulp, repo, session)
    if not base_url:
        logger.error(
            'Post-check failed: cannot find the URL repository %s '
            'is published at',
            uploader.repo_name,
        )
        return False
    logger.info('Downloading published modules.yaml from %s', base_url)
    problems = []
    retries = max(retries, 1)
    for attempt in range(1, retries + 1):
        published, problem = await fetch_published_modules(
            uploader.pulp, base_url
        )
        if problem:
            problems = [problem]
        else:
            problems = compare_modules(uploaded, published, verbose=verbose)
        if published is not None and (not problems or attempt == retries):
            log_modules_summary(uploaded, published, verbose=verbose)
        if not problems:
            logger.info(
                'Post-check passed: published metadata matches the '
                'uploaded one'
            )
            return True
        if attempt < retries:
            logger.warning(
                'Post-check attempt %d/%d found %d difference(s), '
                'retrying in %.1f second(s)',
                attempt,
                retries,
                len(problems),
                delay,
            )
            await asyncio.sleep(delay)
    logger.error('Post-check failed, %d difference(s) found:', len(problems))
    for problem in problems:
        logger.error('  %s', problem)
    return False


def read_metadata_file(path: str) -> str:
    with open(os.path.abspath(os.path.expanduser(path)), 'rt') as fd:
        return fd.read()


def as_upload_file(content: Optional[str]) -> Optional[UploadFile]:
    if content is None:
        return None
    return UploadFile(BytesIO(content.encode('utf-8')))


def parse_args():
    parser = ArgumentParser('metadata-uploader')
    parser.add_argument('-r', '--repo-name', type=str, required=True)
    parser.add_argument('-c', '--comps-file', type=str, required=False)
    parser.add_argument('-m', '--modules-file', type=str, required=False)
    parser.add_argument('-d', '--dry-run', action='store_true')
    parser.add_argument('-v', '--verbose', action='store_true')
    parser.add_argument(
        '--no-post-check',
        dest='post_check',
        action='store_false',
        help=(
            'do not download the published modules.yaml back and compare '
            'it with the uploaded one'
        ),
    )
    parser.add_argument(
        '--post-check-retries',
        type=int,
        default=3,
        help=(
            'how many times to download the published modules.yaml before '
            'reporting a mismatch (default: %(default)s)'
        ),
    )
    parser.add_argument(
        '--post-check-delay',
        type=float,
        default=15.0,
        help=(
            'delay in seconds between post-check attempts '
            '(default: %(default)s)'
        ),
    )
    return parser.parse_args()


async def main():
    args = parse_args()
    log_level = logging.DEBUG if args.verbose else logging.INFO
    logging.basicConfig(level=log_level)
    logger.setLevel(log_level)
    if not args.modules_file and not args.comps_file:
        logger.error('Module or comps file should be specified')
        return EXIT_ERROR
    await setup_all()
    module_content = None
    comps_content = None
    if args.modules_file:
        module_content = read_metadata_file(args.modules_file)
    if args.comps_file:
        comps_content = read_metadata_file(args.comps_file)
    async with get_async_db_session() as session:
        uploader = MetadataUploader(session, args.repo_name)
        await uploader.process_uploaded_files(
            as_upload_file(module_content),
            as_upload_file(comps_content),
            dry_run=args.dry_run,
        )
        if args.dry_run or not args.post_check:
            return EXIT_OK
        if not module_content:
            logger.info('Nothing to post-check, no modules file uploaded')
            return EXIT_OK
        passed = await post_check_modules(
            uploader,
            session,
            module_content,
            retries=args.post_check_retries,
            delay=args.post_check_delay,
            verbose=args.verbose,
        )
    return EXIT_OK if passed else EXIT_POST_CHECK_FAILED


if __name__ == '__main__':
    sys.exit(asyncio.run(main()))

import asyncio
import datetime
import logging
import traceback
import typing
from collections import defaultdict

import sqlalchemy
from fastapi_sqla import open_async_session
from sqlalchemy import delete, func, insert, update
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.orm import selectinload

from alws import models
from alws.config import settings
from alws.constants import (
    BuildTaskStatus,
    GitHubIssueStatus,
)
from alws.crud import build_nodes as build_nodes_crud
from alws.errors import (
    ArtifactChecksumError,
    ArtifactConversionError,
    ModuleUpdateError,
    RepositoryAddError,
    SrpmProvisionError,
)
from alws.schemas import build_node_schema
from alws.schemas.build_node_schema import BuildDoneArtifact
from alws.utils.github_integration_helper import (
    move_issue_to_testing,
)
from alws.utils.ids import get_random_unique_version
from alws.utils.modularity import IndexWrapper, RpmArtifact
from alws.utils.multilib import MultilibProcessor
from alws.utils.noarch import save_noarch_packages
from alws.utils.parsing import clean_release, parse_rpm_nevra
from alws.utils.pulp_client import PulpClient, get_pulp_client
from alws.utils.pulp_utils import get_module_from_pulp_db
from alws.utils.rpm_package import get_rpm_packages_info

# pg_advisory_xact_lock key serializing the node-aware task dispatch
BUILD_TASKS_DISPATCH_LOCK_ID = 0x616C627364697370
# SQLSTATE of lock_timeout expiration, lock_not_available
LOCK_NOT_AVAILABLE = '55P03'
# How many of the dispatchable tasks the balancer fetches at once
BALANCER_CANDIDATES_LIMIT = 100
# How many of the last nodes a task was handed out to are kept
DISPATCH_NODES_LIMIT = 10


def _build_task_load_options():
    return (
        selectinload(models.BuildTask.ref),
        selectinload(models.BuildTask.build).selectinload(models.Build.repos),
        selectinload(models.BuildTask.platform).selectinload(
            models.Platform.repos
        ),
        selectinload(models.BuildTask.build).selectinload(models.Build.owner),
        selectinload(models.BuildTask.build)
        .selectinload(models.Build.linked_builds)
        .selectinload(models.Build.repos),
        selectinload(models.BuildTask.build)
        .selectinload(models.Build.platform_flavors)
        .selectinload(models.PlatformFlavour.repos),
        selectinload(models.BuildTask.artifacts),
        selectinload(models.BuildTask.rpm_modules),
    )


def _excluded_packages_condition(
    excluded_packages: typing.Optional[typing.List[str]],
):
    if not excluded_packages:
        return sqlalchemy.true()
    return sqlalchemy.not_(
        sqlalchemy.or_(*[
            models.BuildTaskRef.url.ilike(f"%{project}%")
            for project in excluded_packages
        ])
    )


def _is_excluded(
    url: str,
    excluded_packages: typing.Optional[typing.List[str]],
) -> bool:
    url = url.lower()
    return any(project.lower() in url for project in excluded_packages or [])


def _record_dispatch(
    task: models.BuildTask,
    node_name: typing.Optional[str],
):
    # dispatch_count isn't increased here: the handout is counted when the
    # node confirms it (see build_nodes.confirmed_dispatch_count), a task
    # the node never got mustn't get closer to being failed.
    # A new list, so the change of the JSONB column is detected
    task.dispatch_nodes = [*(task.dispatch_nodes or []), node_name][
        -DISPATCH_NODES_LIMIT:
    ]


def _dispatches_exhausted(task: models.BuildTask) -> bool:
    limit = settings.build_node_task_max_dispatches
    return limit > 0 and task.dispatch_count >= limit


async def _fail_undeliverable_task(
    db: AsyncSession,
    task: models.BuildTask,
    now: datetime.datetime,
):
    """Fail the task the nodes never sent a result for.

    The nodes took the task, but crash on it, lose it, etc., so it would go
    from node to node forever. It's failed the way the failed build_done
    of a node is, so the dependent tasks, the build and its test tasks
    are processed as usual.
    """
    # alws.dramatiq imports this module
    from alws import dramatiq

    # The names of the nodes are a part of the nodes registry, which is
    # shown to superusers only, and the error of the task is public
    nodes = ', '.join(
        name or '(no node_name)' for name in task.dispatch_nodes or []
    )
    logging.warning(
        'Build task %d was taken by build nodes %d times without '
        'a result, the last nodes it was handed out to: %s. Failing it',
        task.id,
        task.dispatch_count,
        nodes or '(unknown)',
    )
    task.error = (
        f'The task was taken by build nodes {task.dispatch_count} '
        'times without a result'
    )
    # The same state as after build_done: it's not handed out again
    # while dramatiq processes the result
    task.status = BuildTaskStatus.STARTED
    task.ts = now + datetime.timedelta(hours=3)
    task.node_reported_at = now
    await db.flush()
    request = build_node_schema.BuildDone(
        task_id=task.id,
        status='failed',
        artifacts=[],
        stats={},
    )
    actor = dramatiq.build_done
    if task.arch == 'src':
        actor = dramatiq.sources_build_done
    actor.send(request.model_dump())


async def get_available_build_task(
    db: AsyncSession,
    request: build_node_schema.RequestTask,
) -> typing.Optional[models.BuildTask]:
    """Hand out a task to the node.

    A task the nodes took BUILD_NODE_TASK_MAX_DISPATCHES times already is
    failed instead (see _fail_undeliverable_task), and the next one is
    looked for. It covers every way a task goes back to the queue: the
    ping of the node, the reclaim from a dead node and the ts timeout.
    Only the handouts the nodes confirmed are counted (see dispatch_count).
    """
    if request.node_name:
        return await _get_balanced_build_task(db, request)
    return await _get_any_build_task(db, request)


async def _get_any_build_task(
    db: AsyncSession,
    request: build_node_schema.RequestTask,
) -> typing.Optional[models.BuildTask]:
    """Hand out the oldest available task to a node without node_name."""
    # TODO: here should be config value
    ts_expired = datetime.datetime.utcnow() - datetime.timedelta(minutes=20)
    query = (
        select(models.BuildTask)
        .where(~models.BuildTask.dependencies.any())
        .join(
            models.BuildTask.ref,
        )
        # Claiming a task is a queue pop, so it has to be shaped like one:
        #
        #   LIMIT 1   - .first() below only truncates in Python. Without it
        #               the statement returns every eligible task and
        #               FOR UPDATE takes a row lock on each one of them.
        #   SKIP LOCKED - otherwise a second node polling at the same time
        #               blocks on the row the first one is claiming instead
        #               of moving on to the next free task, which caps
        #               dispatch on lock contention rather than on work.
        #   OF build_tasks - the ref join must not be locked as well.
        .with_for_update(skip_locked=True, of=models.BuildTask)
        .limit(1)
        .filter(
            sqlalchemy.and_(
                models.BuildTask.status < BuildTaskStatus.COMPLETED,
                models.BuildTask.arch.in_(request.supported_arches),
                sqlalchemy.or_(
                    models.BuildTask.ts < ts_expired,
                    models.BuildTask.ts.is_(None),
                ),
                _excluded_packages_condition(request.excluded_packages),
            )
        )
        .options(*_build_task_load_options())
        .order_by(models.BuildTask.id.asc())
    )
    while True:
        db_task = (await db.execute(query)).scalars().first()
        if not db_task:
            return
        now = datetime.datetime.utcnow()
        if not _dispatches_exhausted(db_task):
            break
        # Its ts is in the future now, so the query skips it
        await _fail_undeliverable_task(db, db_task, now)
    _record_dispatch(db_task, None)
    db_task.ts = now
    db_task.status = BuildTaskStatus.STARTED
    # The node is unknown, so the task isn't held by any node and
    # its ts is the only thing that keeps it from being handed out again
    db_task.build_node_id = None
    db_task.claimed_at = now
    db_task.claimed_by_instance = None
    db_task.node_reported_at = None
    await db.flush()
    return db_task


def _is_lock_not_available(error: DBAPIError) -> bool:
    # asyncpg errors are wrapped twice: by the SQLAlchemy adapter of the
    # DBAPI and by sqlalchemy.exc.DBAPIError
    for cause in (error.orig, getattr(error.orig, '__cause__', None)):
        if getattr(cause, 'sqlstate', None) == LOCK_NOT_AVAILABLE:
            return True
    return False


async def _lock_dispatch(db: AsyncSession) -> bool:
    """Take the dispatch lock, waiting BUILD_NODE_DISPATCH_LOCK_TIMEOUT.

    Every request waiting for the lock holds a database connection, so it
    can't wait forever: when the lock is busy for that long, False is
    returned and the node asks again later. The lock is held until the end
    of the transaction.

    lock_timeout is set in a savepoint: the failed wait aborts the savepoint
    only, the transaction stays usable and lock_timeout goes back to what it
    was. After the lock is taken lock_timeout is restored, so it doesn't
    limit the other statements of the request.
    """
    timeout_ms = max(1, int(settings.build_node_dispatch_lock_timeout * 1000))
    previous_timeout = (
        await db.execute(select(func.current_setting('lock_timeout')))
    ).scalar_one()
    try:
        async with db.begin_nested():
            await db.execute(
                select(
                    func.set_config('lock_timeout', f'{timeout_ms}ms', True)
                )
            )
            await db.execute(
                select(
                    func.pg_advisory_xact_lock(BUILD_TASKS_DISPATCH_LOCK_ID)
                )
            )
    except DBAPIError as error:
        if not _is_lock_not_available(error):
            raise
        return False
    # The setting of the released savepoint stays in the transaction
    await db.execute(
        select(func.set_config('lock_timeout', previous_timeout, True))
    )
    return True


def _fair_share(
    node: models.BuildNode,
    pool: typing.List[models.BuildNode],
    active_by_node: typing.Dict[int, int],
    queued: int,
) -> int:
    """How many tasks the node may hold while others wait for theirs.

    Nodes that can take the task get slots in proportion to their
    capacity: share = ceil(capacity * min(1, demand / total)), where demand
    is the tasks being built on these nodes plus the queued ones and total
    is their summary capacity. With a long queue the share is the whole
    capacity, so no slot stays idle.
    """
    total = sum(pool_node.effective_capacity for pool_node in pool)
    if total <= 0:
        return 0
    demand = queued + sum(
        active_by_node.get(pool_node.id, 0) for pool_node in pool
    )
    demand = min(demand, total)
    # ceil() in integers
    return -(-node.effective_capacity * demand // total)


async def _claim_build_task(
    db: AsyncSession,
    task_id: int,
    node: models.BuildNode,
    now: datetime.datetime,
    instance_id: typing.Optional[str],
) -> typing.Optional[models.BuildTask]:
    # Nodes without node_name don't take the advisory lock, so the task
    # could be claimed by one of them since it was picked as a candidate
    result = await db.execute(
        select(models.BuildTask)
        .where(
            models.BuildTask.id == task_id,
            ~models.BuildTask.dependencies.any(),
            build_nodes_crud.dispatchable_task_condition(now),
        )
        .with_for_update(skip_locked=True, of=models.BuildTask)
        .options(*_build_task_load_options())
        .execution_options(populate_existing=True)
    )
    db_task = result.scalars().first()
    if not db_task:
        return
    if _dispatches_exhausted(db_task):
        await _fail_undeliverable_task(db, db_task, now)
        return
    _record_dispatch(db_task, node.name)
    db_task.status = BuildTaskStatus.STARTED
    db_task.ts = now
    db_task.build_node_id = node.id
    db_task.claimed_at = now
    db_task.claimed_by_instance = instance_id
    db_task.node_reported_at = None
    await db.flush()
    return db_task


async def _get_balanced_build_task(
    db: AsyncSession,
    request: build_node_schema.RequestTask,
) -> typing.Optional[models.BuildTask]:
    """Hand out a task to a registered node, balancing the nodes load.

    The node gets the oldest task it can build only while it holds less
    than its fair share of tasks (see _fair_share). A task waiting longer
    than BUILD_NODE_BALANCER_MAX_WAIT goes to any node with a free slot.
    """
    # The decision depends on what the other nodes hold,
    # so the node-aware dispatch is serialized
    if not await _lock_dispatch(db):
        logging.warning(
            'Build node %s gets no task: the dispatch lock is busy '
            'for longer than %s seconds',
            request.node_name,
            settings.build_node_dispatch_lock_timeout,
        )
        return
    now = datetime.datetime.utcnow()
    node = await build_nodes_crud.register_build_node(
        db,
        request.node_name,
        now,
        node_info=request.node_info,
        supported_arches=request.supported_arches,
        excluded_packages=request.excluded_packages or [],
    )
    if not node.accepts_tasks():
        return
    # Not saved in the node, the instance change is handled by ping
    instance_id = request.node_info.instance_id if request.node_info else None
    active_by_node = await build_nodes_crud.count_active_tasks_by_node(db)
    node_active = active_by_node.get(node.id, 0)
    if node_active >= node.effective_capacity:
        return

    secure_boot_condition = sqlalchemy.true()
    if not node.pesign_support:
        secure_boot_condition = sqlalchemy.or_(
            models.BuildTask.is_secure_boot.is_(None),
            models.BuildTask.is_secure_boot.is_(False),
        )
    dispatchable = build_nodes_crud.dispatchable_task_condition(now)
    candidates_query = (
        select(
            models.BuildTask.id,
            models.BuildTask.arch,
            models.BuildTask.is_secure_boot,
            models.BuildTask.queued_at,
            models.BuildTaskRef.url,
        )
        .join(models.BuildTask.ref)
        .where(
            ~models.BuildTask.dependencies.any(),
            models.BuildTask.arch.in_(request.supported_arches),
            _excluded_packages_condition(request.excluded_packages),
            secure_boot_condition,
            dispatchable,
        )
        .order_by(models.BuildTask.id.asc())
        .limit(BALANCER_CANDIDATES_LIMIT)
    )
    candidates = (await db.execute(candidates_query)).all()
    if not candidates:
        return

    queued_by_arch = await db.execute(
        select(models.BuildTask.arch, func.count())
        .where(
            ~models.BuildTask.dependencies.any(),
            models.BuildTask.arch.in_(request.supported_arches),
            dispatchable,
        )
        .group_by(models.BuildTask.arch)
    )
    queued_by_arch = dict(queued_by_arch.all())
    other_nodes = [
        other
        for other in await build_nodes_crud.get_all_build_nodes(db)
        if other.id != node.id
        and other.accepts_tasks()
        and other.is_online(now)
    ]
    max_wait_border = now - datetime.timedelta(
        seconds=settings.build_node_balancer_max_wait,
    )
    shares = {}
    # The node may be at its share for the oldest tasks while a task further
    # in the queue is starving or has a pool of its own (an arch, a secure
    # boot or an excluded package the other nodes can't take), so the whole
    # queue is looked through. A task is skipped only while the queue of its
    # arch is shorter than the pool capacity (otherwise the share is the
    # whole capacity, see _fair_share), so the scan is bounded by the nodes
    # capacity per arch and not by the queue length.
    while candidates:
        for task in candidates:
            starving = (
                task.queued_at is None or task.queued_at <= max_wait_border
            )
            if not starving:
                # The pool of nodes that could build the task right now
                pool = [node] + [
                    other
                    for other in other_nodes
                    if task.arch in (other.supported_arches or [])
                    and (not task.is_secure_boot or other.pesign_support)
                    and not _is_excluded(task.url, other.excluded_packages)
                ]
                pool_key = (task.arch, tuple(other.id for other in pool))
                if pool_key not in shares:
                    shares[pool_key] = _fair_share(
                        node,
                        pool,
                        active_by_node,
                        queued_by_arch.get(task.arch, 0),
                    )
                if node_active >= shares[pool_key]:
                    continue
            db_task = await _claim_build_task(
                db,
                task.id,
                node,
                now,
                instance_id,
            )
            if db_task:
                return db_task
        if len(candidates) < BALANCER_CANDIDATES_LIMIT:
            return
        candidates = (
            await db.execute(
                candidates_query.where(
                    models.BuildTask.id > candidates[-1].id,
                )
            )
        ).all()


def add_build_task_dependencies(
    db: AsyncSession,
    task: models.BuildTask,
    last_task: models.BuildTask,
):
    task.dependencies.append(last_task)


async def get_failed_build_tasks_matrix(db: AsyncSession, build_id: int):
    build_tasks = await db.execute(
        select(models.BuildTask)
        .where(
            models.BuildTask.build_id == build_id,
            models.BuildTask.status <= BuildTaskStatus.FAILED,
        )
        .order_by(models.BuildTask.index, models.BuildTask.id)
    )

    tasks_matrix = {}
    for task in build_tasks.scalars().all():
        idx = task.index
        platform_id = task.platform_id
        arch = task.arch
        matrix_key = (platform_id, arch)
        if idx not in tasks_matrix:
            tasks_matrix[idx] = defaultdict(dict)
        tasks_matrix[idx][matrix_key] = task

    failed_matrix = {}
    for idx in tasks_matrix:
        for matrix_key in tasks_matrix[idx]:
            if tasks_matrix[idx][matrix_key].status == BuildTaskStatus.FAILED:
                failed_matrix[len(failed_matrix)] = tasks_matrix[idx]
                break

    return failed_matrix


async def update_failed_build_items_in_parallel(
    db: AsyncSession,
    build_id: int,
):
    tasks_cache = await get_failed_build_tasks_matrix(db, build_id)
    tasks_indexes = list(tasks_cache.keys())
    for task_index, index_dict in tasks_cache.items():
        current_idx = tasks_indexes.index(task_index)
        first_index_dep = None

        completed_index_tasks = []
        failed_tasks = []
        for task in index_dict.values():
            if task.status == BuildTaskStatus.COMPLETED:
                completed_index_tasks.append(task)
            elif task.status == BuildTaskStatus.FAILED:
                failed_tasks.append(task)

        drop_srpm = False
        if len(failed_tasks) == len(index_dict):
            drop_srpm = True

        for key in sorted(
            list(index_dict.keys()),
            key=lambda x: x[1] == "src",
            reverse=True,
        ):
            task = index_dict[key]
            if task.status != BuildTaskStatus.FAILED:
                continue
            if task.built_srpm_url and drop_srpm:
                task.built_srpm_url = None
            task.status = BuildTaskStatus.IDLE
            task.ts = None
            task.queued_at = datetime.datetime.utcnow()
            # A user restarted the task, it gets all the attempts again
            task.dispatch_count = 0
            task.dispatch_nodes = None
            if first_index_dep:
                await db.run_sync(
                    add_build_task_dependencies, task, first_index_dep
                )
            idx = current_idx - 1
            while idx >= 0:
                prev_task_index = tasks_indexes[idx]
                dep = tasks_cache.get(prev_task_index, {}).get(key)
                # dependency.status can be completed because
                # we stores in cache completed tasks
                if dep and dep.status == BuildTaskStatus.IDLE:
                    await db.run_sync(add_build_task_dependencies, task, dep)
                idx -= 1
            # if at least one task in index is completed,
            # we shouldn't wait first task completion
            if first_index_dep is None and not completed_index_tasks:
                first_index_dep = task
    await db.flush()


async def update_failed_build_items(db: AsyncSession, build_id: int):
    failed_tasks_matrix = await get_failed_build_tasks_matrix(db, build_id)

    last_task = None
    for tasks_dicts in failed_tasks_matrix.values():
        failed_tasks = [
            task
            for task in tasks_dicts.values()
            if task.status == BuildTaskStatus.FAILED
        ]
        drop_srpm = False
        if len(failed_tasks) == len(tasks_dicts):
            drop_srpm = True

        for task in failed_tasks:
            if task.built_srpm_url and drop_srpm:
                task.built_srpm_url = None
            task.status = BuildTaskStatus.IDLE
            task.ts = None
            task.queued_at = datetime.datetime.utcnow()
            # A user restarted the task, it gets all the attempts again
            task.dispatch_count = 0
            task.dispatch_nodes = None
            if last_task is not None:
                await db.run_sync(add_build_task_dependencies, task, last_task)
            last_task = task
        await db.flush()


async def mark_build_tasks_as_cancelled(
    session: AsyncSession,
    build_id: int,
):
    await session.execute(
        update(models.BuildTask)
        .where(
            models.BuildTask.build_id == build_id,
            models.BuildTask.status == BuildTaskStatus.IDLE,
        )
        .values(
            status=BuildTaskStatus.CANCELLED,
            error="Build task cancelled by user",
        )
    )


async def log_repo_exists(db: AsyncSession, task: models.BuildTask):
    repo = await db.execute(
        select(models.Repository).where(
            models.Repository.name == task.get_log_repo_name()
        )
    )
    return bool(repo.scalars().first())


async def create_build_log_repo(db: AsyncSession, task: models.BuildTask):
    pulp_client = get_pulp_client()
    repo_name = task.get_log_repo_name()
    pulp_repo = await pulp_client.get_log_repository(repo_name)
    if pulp_repo:
        pulp_href = pulp_repo["pulp_href"]
        distro = await pulp_client.get_log_distro(repo_name)
        if not distro:
            repo_url = await pulp_client.create_file_distro(
                repo_name, pulp_href
            )
        else:
            repo_url = distro["base_url"]
    else:
        repo_url, pulp_href = await pulp_client.create_log_repo(repo_name)
    if await log_repo_exists(db, task):
        return
    log_repo = models.Repository(
        name=repo_name,
        url=repo_url,
        arch=task.arch,
        pulp_href=pulp_href,
        type="build_log",
        debug=False,
    )
    db.add(log_repo)
    await db.flush()
    await db.refresh(log_repo)
    await db.execute(
        insert(models.BuildRepo).values(
            build_id=task.build_id, repository_id=log_repo.id
        )
    )
    await db.flush()


async def ping_tasks(db: AsyncSession, task_list: typing.List[int]):
    """Refresh the tasks reported by a node without node_name.

    The first report of a task confirms its handout (see dispatch_count).
    """
    query = models.BuildTask.id.in_(task_list)
    now = datetime.datetime.utcnow()
    await db.execute(
        update(models.BuildTask)
        .where(query)
        .values(
            ts=now,
            dispatch_count=build_nodes_crud.confirmed_dispatch_count(),
        )
    )
    await db.flush()


async def ping_build_node(db: AsyncSession, ping: build_node_schema.Ping):
    """Register the node and reconcile its tasks with what it reported.

    Only the tasks held by the node get their ts refreshed, the first report
    of a task confirms its handout (see dispatch_count). Its tasks that
    the node doesn't report anymore (it was restarted, lost them, etc.)
    go back to the queue, unless they were handed out too recently to be
    in the ping yet.

    Nothing is returned to the queue while another instance of the node
    may be running: two instances run with the same name and each of them
    would return the tasks of the other one. The instance is considered
    another one when it differs from the last one, unless the node was
    silent for the offline timeout while the server was working, and
    the reconciliation is off for the offline timeout after the last such
    change. Two instances running in parallel keep it off for as long as
    they run, a warning is logged on each change.

    A restart is confirmed when the new instance names the last one as
    its previous_instance_id (the node keeps it in a file, which another
    host with the same name doesn't have). The reconciliation stays on
    then, and the tasks the new instance didn't claim (the tasks of the
    previous one) are returned to the queue at once, without the grace.

    get_task doesn't save the instance, so the change is always seen here,
    even when the new instance asked for a task before its first ping.
    The tasks it got are told by claimed_by_instance and keep the grace.
    """
    now = datetime.datetime.utcnow()
    instance_id = None
    previous_instance_id = None
    if ping.node_info:
        instance_id = ping.node_info.instance_id
        previous_instance_id = ping.node_info.previous_instance_id
    # Locked, so concurrent pings of two instances see each other
    previous = await build_nodes_crud.get_build_node_by_name(
        db,
        ping.node_name,
        for_update=True,
    )
    instance_changed_at = None
    confirmed_restart = False
    if previous is not None:
        instance_changed_at = previous.instance_changed_at
        if (
            instance_id is not None
            # A node that didn't send its instance before isn't another one
            and previous.instance_id is not None
            and instance_id != previous.instance_id
        ):
            confirmed_restart = previous_instance_id == previous.instance_id
            # Not just "isn't online": after a downtime of the server
            # every node looks offline, while both instances may be alive
            if previous.is_silent_for(
                now,
                settings.build_node_offline_timeout,
                await build_nodes_crud.server_seen_since(db, now),
            ):
                # Just a restart of the node, the previous instance is gone
                instance_changed_at = None
            elif confirmed_restart:
                # instance_changed_at is kept: if another instance showed
                # up recently, it may still be running
                logging.info(
                    "Build node %s was restarted, instance %s replaced %s",
                    ping.node_name,
                    instance_id,
                    previous.instance_id,
                )
            else:
                instance_changed_at = now
                logging.warning(
                    "Build node %s was seen with instance %s, but ping "
                    "came from instance %s. Two instances of the node may "
                    "be running with the same name, its tasks aren't "
                    "returned to the queue",
                    ping.node_name,
                    previous.instance_id,
                    instance_id,
                )
    node = await build_nodes_crud.register_build_node(
        db,
        ping.node_name,
        now,
        node_info=ping.node_info,
        resources=ping.resources,
        instance_id=instance_id,
        instance_changed_at=instance_changed_at,
    )
    reconcile = not node.instance_changed_recently(now)
    active_tasks = set(ping.active_tasks)
    if active_tasks:
        # Tasks the node took before it started to send node_name
        await db.execute(
            update(models.BuildTask)
            .where(
                models.BuildTask.id.in_(active_tasks),
                models.BuildTask.build_node_id.is_(None),
                models.BuildTask.status == BuildTaskStatus.STARTED,
                models.BuildTask.node_reported_at.is_(None),
            )
            .values(
                build_node_id=node.id,
                claimed_at=func.coalesce(models.BuildTask.claimed_at, now),
                claimed_by_instance=instance_id,
            )
        )
        await db.execute(
            update(models.BuildTask)
            .where(
                models.BuildTask.id.in_(active_tasks),
                models.BuildTask.build_node_id == node.id,
                build_nodes_crud.held_by_node_condition(),
            )
            # The first report of a task confirms the node got it
            .values(
                ts=now,
                dispatch_count=build_nodes_crud.confirmed_dispatch_count(),
            )
        )
    if not reconcile:
        await db.flush()
        return
    grace_border = now - datetime.timedelta(
        seconds=settings.build_node_reconcile_grace,
    )
    out_of_grace = [
        models.BuildTask.claimed_at.is_(None),
        models.BuildTask.claimed_at < grace_border,
    ]
    if confirmed_restart:
        # The previous instance is gone, it won't report its tasks
        out_of_grace.append(
            models.BuildTask.claimed_by_instance.is_distinct_from(instance_id)
        )
    lost_tasks_condition = [
        models.BuildTask.build_node_id == node.id,
        build_nodes_crud.held_by_node_condition(),
        sqlalchemy.or_(*out_of_grace),
    ]
    if active_tasks:
        lost_tasks_condition.append(
            models.BuildTask.id.not_in(active_tasks),
        )
    lost_tasks = await db.execute(
        update(models.BuildTask)
        .where(*lost_tasks_condition)
        .values(
            status=BuildTaskStatus.IDLE,
            build_node_id=None,
            ts=None,
            claimed_at=None,
            claimed_by_instance=None,
            queued_at=now,
        )
        .returning(models.BuildTask.id)
    )
    lost_tasks = lost_tasks.scalars().all()
    if lost_tasks:
        logging.warning(
            "Build node %s doesn't report tasks %s anymore, "
            "returning them to the queue",
            node.name,
            lost_tasks,
        )
    await db.flush()


async def mark_dependent_tasks_queued(
    db: AsyncSession,
    task_ids: typing.Iterable[int],
):
    """Tasks waiting for the given ones may become ready to be handed out.

    Has to be called before the dependencies are removed. A task is ready
    once its last dependency is removed, so the latest call wins.
    """
    dependent_tasks = select(models.BuildTaskDependency.c.build_task_id).where(
        models.BuildTaskDependency.c.build_task_dependency.in_(list(task_ids)),
    )
    await db.execute(
        update(models.BuildTask)
        .where(models.BuildTask.id.in_(dependent_tasks))
        .values(queued_at=datetime.datetime.utcnow())
        .execution_options(synchronize_session=False)
    )


async def get_build_task(
    db: AsyncSession,
    task_id: int,
    for_update: bool = False,
) -> models.BuildTask:
    query = (
        select(models.BuildTask)
        .where(models.BuildTask.id == task_id)
        .options(selectinload(models.BuildTask.platform))
    )
    if for_update:
        query = query.with_for_update(of=models.BuildTask).execution_options(
            populate_existing=True,
        )
    build_tasks = await db.execute(query)
    return build_tasks.scalars().first()


def __verify_checksums(
    processed_entities: typing.List[
        typing.Tuple[str, str, build_node_schema.BuildDoneArtifact]
    ],
):
    checksum_errors = []
    for _, sha256, artifact in processed_entities:
        if sha256 != artifact.sha256:
            checksum_errors.append(
                f"{str(artifact.name)} has incorrect checksum: "
                f"reported {artifact.sha256}, Pulp has {sha256}"
            )
    if checksum_errors:
        raise ArtifactChecksumError("\n".join(checksum_errors))


async def get_srpm_artifact_by_build_task_id(
    db: AsyncSession,
    build_task_id: int,
) -> models.BuildTaskArtifact:
    srpm_artifact = await db.execute(
        select(models.BuildTaskArtifact).where(
            models.BuildTaskArtifact.build_task_id == build_task_id,
            models.BuildTaskArtifact.name.like("%.src.rpm"),
            models.BuildTaskArtifact.type == "rpm",
        ),
    )
    return srpm_artifact.scalars().first()


async def __process_rpms(
    db: AsyncSession,
    pulp_client: PulpClient,
    build_id: int,
    task_id: int,
    task_arch: str,
    task_artifacts: list,
    repositories: list,
    built_srpm_url: str = None,
    module_index=None,
    task_excluded=False,
):
    def get_repo(repo_arch, is_debug):
        return next(
            build_repo
            for build_repo in repositories
            if build_repo.arch == repo_arch
            and build_repo.type == "rpm"
            and build_repo.debug == is_debug
        )

    arch_repo = None
    debug_repo = None
    if task_arch != 'src':
        arch_repo = get_repo(task_arch, False)
        debug_repo = get_repo(task_arch, True)
    src_repo = get_repo("src", False)
    arch_packages_tasks = []
    src_packages_tasks = []
    debug_packages_tasks = []
    for artifact in task_artifacts:
        if task_arch == 'src':
            if artifact.arch == "src":
                src_packages_tasks.append(pulp_client.create_entity(artifact))
                break
            continue
        if artifact.arch == "src":
            if built_srpm_url is None:
                src_packages_tasks.append(pulp_client.create_entity(artifact))
        elif artifact.is_debuginfo:
            debug_packages_tasks.append(pulp_client.create_entity(artifact))
        else:
            arch_packages_tasks.append(pulp_client.create_entity(artifact))

    processed_packages = []
    for tasks, repo in (
        (src_packages_tasks, src_repo),
        (arch_packages_tasks, arch_repo),
        (debug_packages_tasks, debug_repo),
    ):
        if not tasks:
            continue
        try:
            results = await asyncio.gather(*tasks)
        except Exception as e:
            logging.exception(
                "Cannot create RPM packages for repo %s", str(repo)
            )
            raise ArtifactConversionError(
                f"Cannot put RPM packages into Pulp storage: {e}"
            )
        processed_packages.extend(results)
        hrefs = [item[0] for item in results]
        __verify_checksums(processed_packages)
        try:
            await pulp_client.modify_repository(repo.pulp_href, add=hrefs)
        except Exception:
            logging.exception(
                "Cannot add RPM packages to the repository: %s", str(repo)
            )
            raise RepositoryAddError(
                f"Cannot add RPM packages to the repository {str(repo)}"
            )

    rpms = [
        models.BuildTaskArtifact(
            build_task_id=task_id,
            name=artifact.name,
            type=artifact.type,
            href=href,
            cas_hash=artifact.cas_hash,
        )
        for href, _, artifact in processed_packages
    ]

    rpms_info = get_rpm_packages_info(rpms)
    for rpm in rpms:
        rpm_info = rpms_info[rpm.href]
        meta = {
            "name": rpm_info["name"],
            "epoch": rpm_info["epoch"],
            "version": rpm_info["version"],
            "release": rpm_info["release"],
            "arch": rpm_info["arch"],
            "sha256": rpm_info["sha256"],
        }
        rpm.meta = meta

    errata_record_ids = set()
    for build_task_artifact in rpms:
        rpm_info = rpms_info[build_task_artifact.href]
        if rpm_info["arch"] != "src":
            src_name = parse_rpm_nevra(rpm_info["rpm_sourcerpm"]).name
        else:
            src_name = rpm_info["name"]
        clean_rpm_release = clean_release(rpm_info["release"])
        conditions = [
            models.NewErrataPackage.name == rpm_info["name"],
            models.NewErrataPackage.version == rpm_info["version"],
        ]
        if rpm_info["arch"] != "noarch":
            conditions.append(models.NewErrataPackage.arch == rpm_info["arch"])

        query = select(models.NewErrataPackage).where(
            sqlalchemy.and_(*conditions)
        )

        if module_index:
            module = None
            for mod in module_index.iter_modules():
                if mod.name.endswith("-devel"):
                    continue
                module = mod
            build_task_module = f"{module.name}:{module.stream}"
            query = query.join(models.NewErrataRecord).filter(
                models.NewErrataRecord.module == build_task_module
            )

        errata_packages = (await db.execute(query)).scalars().all()

        for errata_package in errata_packages:
            if clean_rpm_release != clean_release(errata_package.release):
                continue
            errata_record_ids.add(errata_package.errata_record_id)

    if settings.github_integration_enabled and errata_record_ids:
        try:
            await move_issue_to_testing(
                record_ids=list(errata_record_ids),
                build_id=build_id,
            )
        except Exception as err:
            logging.exception(
                "Cannot move issue to the Testing section: %s",
                err,
            )

    # we need to put source RPM in module as well, but it can be skipped
    # because it's built before
    module_artifacts = [rpms_info[rpm.href] for rpm in rpms]
    if built_srpm_url is not None:
        db_srpm = await get_srpm_artifact_by_build_task_id(db, task_id)
        if db_srpm is not None:
            srpms_info = get_rpm_packages_info([db_srpm])
            module_artifacts.append(srpms_info[db_srpm.href])
    if module_index and module_artifacts:
        try:
            for module in module_index.iter_modules():
                for artifact in module_artifacts:
                    module.add_rpm_artifact(
                        artifact, task_excluded=task_excluded
                    )
        except Exception as e:
            raise ModuleUpdateError("Cannot update module: %s", str(e)) from e

    return rpms


async def __process_logs(
    pulp_client: PulpClient,
    task_id: int,
    task_artifacts: list,
    repository: models.Repository,
):
    # A task failed by the server has no logs, Pulp needn't be called
    if not task_artifacts:
        return []
    if not repository:
        logging.error("Log repository is absent, skipping logs processing")
        return
    logs = []
    tasks = [pulp_client.create_entity(artifact) for artifact in task_artifacts]
    try:
        results = await asyncio.gather(*tasks)
    except Exception as e:
        logging.exception("Cannot create log files for %s", str(repository))
        raise ArtifactConversionError(
            f"Cannot create log files for {str(repository)}, error: {str(e)}"
        )

    __verify_checksums(results)

    hrefs = []
    for href, _, artifact in results:
        logs.append(
            models.BuildTaskArtifact(
                build_task_id=task_id,
                name=artifact.name,
                type=artifact.type,
                href=href,
                cas_hash=artifact.cas_hash,
            )
        )
        hrefs.append(href)
    try:
        await pulp_client.modify_repository(repository.pulp_href, add=hrefs)
    except Exception as e:
        logging.exception("Cannot add log files to the repository: %s", str(e))
        raise RepositoryAddError(
            "Cannot save build log into Pulp repository: %s", str(e)
        )
    return logs


# TODO: Improve readability
#  * Split into smaller pieces
#  * Maybe use decorators for stats
async def __process_build_task_artifacts(
    db: AsyncSession,
    pulp_client: PulpClient,
    task_id: int,
    task_artifacts: list[BuildDoneArtifact],
    status: BuildTaskStatus,
    git_commit_hash: typing.Optional[str],
) -> typing.Tuple[models.BuildTask, typing.Dict[str, typing.Dict[str, str]]]:
    def _get_srpm_name(
        artifacts: list[BuildDoneArtifact],
        task: models.BuildTask,
    ) -> str:
        srpm_url = task.built_srpm_url
        srpm_name = next(
            (
                artifact.name
                for artifact in artifacts
                if artifact.arch == "src" and artifact.type == "rpm"
            ),
            # We extract a source RPM name from its URL
            # if sRPM is absent in artifacts
            # URL looks like
            # AlmaLinux-9-src-20-br/Packages/b/bind-9.16.23-11.el9_2.1.src.rpm
            srpm_url.rsplit(sep='/', maxsplit=1)[-1] if srpm_url else None,
        )
        return srpm_name

    processing_stats = {}
    build_task = (
        (
            await db.execute(
                select(models.BuildTask)
                .where(models.BuildTask.id == task_id)
                .with_for_update()
                .options(
                    selectinload(models.BuildTask.platform).selectinload(
                        models.Platform.reference_platforms
                    ),
                    selectinload(models.BuildTask.rpm_modules),
                    selectinload(models.BuildTask.ref),
                    selectinload(models.BuildTask.build).selectinload(
                        models.Build.repos
                    ),
                )
            )
        )
        .scalars()
        .first()
    )
    module_index = None
    module_repo = None
    query = (
        select(models.Repository)
        .join(models.BuildRepo)
        .where(
            models.BuildRepo.c.build_id == build_task.build_id,
        )
    )
    rpm_repositories = (
        (
            await db.execute(
                query.where(
                    models.Repository.platform_id == build_task.platform_id,
                    models.Repository.type == 'rpm',
                )
            )
        )
        .scalars()
        .all()
    )
    log_repository = (
        (
            await db.execute(
                query.where(
                    models.Repository.type == 'build_log',
                )
            )
        )
        .scalars()
        .first()
    )
    if git_commit_hash:
        build_task.ref.git_commit_hash = git_commit_hash
    if build_task.rpm_modules:
        module_repo = next(
            build_repo
            for build_repo in rpm_repositories
            if build_repo.arch == build_task.arch and build_repo.debug is False
        )
        try:
            repo_modules_yaml = await pulp_client.get_repo_modules_yaml(
                module_repo.url
            )
            module_index = IndexWrapper.from_template(repo_modules_yaml)
        except Exception as e:
            message = f"Cannot parse modules index: {str(e)}"
            logging.exception("Cannot parse modules index: %s", str(e))
            raise ModuleUpdateError(message) from e
    rpm_artifacts = [item for item in task_artifacts if item.type == "rpm"]
    log_artifacts = [
        item for item in task_artifacts if item.type == "build_log"
    ]
    src_rpm = _get_srpm_name(
        artifacts=task_artifacts,
        task=build_task,
    )
    # If we have RPM artifacts but missing source RPM
    # then we should throw an error
    if not src_rpm and not build_task.built_srpm_url and rpm_artifacts:
        message = "No source RPM was sent from build node"
        logging.error(message)
        raise SrpmProvisionError(message)
    # Committing logs separately for UI to be able to fetch them
    logging.info("Processing logs")
    start_time = datetime.datetime.utcnow()
    logs_entries = await __process_logs(
        pulp_client, build_task.id, log_artifacts, log_repository
    )
    if logs_entries:
        db.add_all(logs_entries)
        await db.flush()
    end_time = datetime.datetime.utcnow()
    processing_stats["logs_processing"] = {
        "start_ts": str(start_time),
        "end_ts": str(end_time),
        "delta": str(end_time - start_time),
    }
    logging.info("Logs processing is finished")
    logging.info("Processing packages")
    start_time = datetime.datetime.utcnow()
    rpm_entries = await __process_rpms(
        db,
        pulp_client,
        build_task.build_id,
        build_task.id,
        build_task.arch,
        rpm_artifacts,
        rpm_repositories,
        built_srpm_url=build_task.built_srpm_url,
        module_index=module_index,
        task_excluded=status.value == BuildTaskStatus.EXCLUDED,
    )
    end_time = datetime.datetime.utcnow()
    processing_stats["packages_processing"] = {
        "start_ts": str(start_time),
        "end_ts": str(end_time),
        "delta": str(end_time - start_time),
    }
    logging.info("Packages processing is finished")
    multilib_conditions = (
        src_rpm is not None,
        build_task.arch == "x86_64",
        status == BuildTaskStatus.COMPLETED,
        bool(settings.beholder_host),
        bool(settings.package_beholder_enabled),
        # TODO: Beholder doesn't have authorization right now
        # bool(settings.beholder_token),
    )
    if all(multilib_conditions):
        processor = MultilibProcessor(
            db, build_task, pulp_client=pulp_client, module_index=module_index
        )
        logging.info("Processing multilib packages")
        start_time = datetime.datetime.utcnow()
        multilib_packages = await processor.get_packages(src_rpm)
        if module_index:
            multilib_module_artifacts = await processor.get_module_artifacts()
            multilib_packages.update(
                {i["name"]: i["version"] for i in multilib_module_artifacts}
            )
            await processor.add_multilib_packages(multilib_packages)
            parsed_src = RpmArtifact.from_str(src_rpm)
            await processor.add_multilib_module_artifacts(
                src_name=parsed_src.name,
                prepared_artifacts=multilib_module_artifacts,
            )
        else:
            await processor.add_multilib_packages(multilib_packages)
        end_time = datetime.datetime.utcnow()
        processing_stats["multilib_processing"] = {
            "start_ts": str(start_time),
            "end_ts": str(end_time),
            "delta": str(end_time - start_time),
        }
        logging.info("Multilib packages processing is finished")
    old_modules = []
    new_modules = []
    logging.info("Starting modules update in Pulp")
    logging.info(f"Task rpm modules: %s", build_task.rpm_modules)
    logging.info(f"Module index: %s", module_index)
    if build_task.rpm_modules and module_index:
        # If the task is the last for its architecture, we need to add
        # correct version for it in Pulp
        arch_task_statuses = (
            (
                await db.execute(
                    select(models.BuildTask.status).where(
                        models.BuildTask.arch == build_task.arch,
                        models.BuildTask.build_id == build_task.build_id,
                        models.BuildTask.id != build_task.id,
                    )
                )
            )
            .scalars()
            .all()
        )
        finished_states = (
            BuildTaskStatus.CANCELLED,
            BuildTaskStatus.COMPLETED,
            BuildTaskStatus.EXCLUDED,
            BuildTaskStatus.FAILED,
        )

        for rpm_module in build_task.rpm_modules:
            logging.info("Processing module template for %s", rpm_module.name)
            start_time = datetime.datetime.utcnow()
            # If all build tasks are finished, module_version will be
            # the final (or real) one.
            # If there are unfinished build tasks, module_version will be
            # a randomly generated version.
            if all((i in finished_states for i in arch_task_statuses)):
                module_version = rpm_module.version
            else:
                module_version = get_random_unique_version()

            try:
                module_for_pulp = module_index.get_module(
                    rpm_module.name,
                    rpm_module.stream,
                )
                logging.debug("final module version: %s", rpm_module.version)
                logging.debug(
                    "current version in repo %s",
                    module_for_pulp.version,
                )
                logging.debug(
                    "about to set module version to %s",
                    module_version,
                )
                # If the final module is already in pulp, it's because we are
                # rebuilding failed tasks. At this point, we delete the current
                # module in pulp db and a new final one will be properly
                # created/pubished below.
                async with open_async_session('pulp_async') as pulp_db:
                    module_in_pulp_db = await get_module_from_pulp_db(
                        pulp_db,
                        rpm_module,
                    )
                    if (
                        rpm_module.version == str(module_for_pulp.version)
                        and module_in_pulp_db
                    ):
                        logging.info(
                            "Module already exists in Pulp, delete current one ("
                            f"{rpm_module.name}:{rpm_module.stream}:"
                            f"{rpm_module.version}:"
                            f"{rpm_module.context}:{rpm_module.arch}) "
                            "before adding the new one."
                        )
                        await pulp_db.delete(module_in_pulp_db)

                module_for_pulp.version = int(module_version)
                module_pulp_href = await pulp_client.create_module(
                    module_for_pulp.render(),
                    rpm_module.name,
                    rpm_module.stream,
                    rpm_module.context,
                    rpm_module.arch,
                    module_for_pulp.description,
                    version=module_version,
                    artifacts=module_for_pulp.get_rpm_artifacts(),
                    dependencies=list(
                        module_for_pulp.get_runtime_deps().values()
                    ),
                    # packages=module_pkgs_hrefs,
                    packages=[],
                    profiles=module_for_pulp.get_profiles(),
                )
                # Here we ensure that we add the recently created module
                # and remove the old module (if any) from the build repo
                # later on at modify_repository.
                new_modules.append(module_pulp_href)
                old_modules.append(rpm_module.pulp_href)
                rpm_module.pulp_href = module_pulp_href
                end_time = datetime.datetime.utcnow()
                processing_stats["module_processing"] = {
                    "start_ts": str(start_time),
                    "end_ts": str(end_time),
                    "delta": str(end_time - start_time),
                }
            except Exception as e:
                message = (
                    f"Cannot update module information inside Pulp: {str(e)}"
                )
                logging.exception(message)
                raise ModuleUpdateError(message) from e
            logging.info("Module template processing is finished")
        await pulp_client.modify_repository(
            module_repo.pulp_href,
            add=new_modules,
            remove=old_modules,
        )

    if rpm_entries:
        db.add_all(rpm_entries)
    db.add(build_task)
    await db.flush()
    await db.refresh(build_task, attribute_names=['build'])
    return build_task, processing_stats


async def __update_built_srpm_url(
    db: AsyncSession,
    build_task: models.BuildTask,
    request: build_node_schema.BuildDone,
):
    # Only first task in a row could have SRPM url not set.
    # All other tasks will be either having it already or fast-failed,
    # so should not call this function anyway.
    if build_task.built_srpm_url:
        return
    uncompleted_tasks_ids = []
    if BuildTaskStatus.is_finished(build_task.status):
        uncompleted_tasks_ids = await db.execute(
            select(models.BuildTask.id).where(
                models.BuildTask.id != build_task.id,
                models.BuildTask.ref_id == build_task.ref_id,
                models.BuildTask.status == BuildTaskStatus.IDLE,
                models.BuildTask.platform_id == build_task.platform_id,
            )
        )
        uncompleted_tasks_ids = uncompleted_tasks_ids.scalars().all()

    # Check if SRPM exists even if task is failed
    srpm_artifact = await get_srpm_artifact_by_build_task_id(db, build_task.id)

    # if SRPM isn't built in first arch of project, we need to stop building
    # the project and fast-fail the uncompleted tasks
    if (
        not srpm_artifact
        and build_task.status == BuildTaskStatus.FAILED
        and uncompleted_tasks_ids
    ):
        # Set the error field to describe the reason why they are fast failing
        fast_fail_msg = (
            "Fast failed: SRPM build failed in the initial "
            f"architecture ({build_task.arch}). "
            "Please refer to the initial architecture build "
            "logs for more information about the failure."
        )
        update_query = (
            update(models.BuildTask)
            .where(
                models.BuildTask.id.in_(uncompleted_tasks_ids),
            )
            .values(status=BuildTaskStatus.FAILED, error=fast_fail_msg)
        )
        await db.execute(update_query)

        await mark_dependent_tasks_queued(db, uncompleted_tasks_ids)
        remove_query = delete(models.BuildTaskDependency).where(
            models.BuildTaskDependency.c.build_task_dependency.in_(
                uncompleted_tasks_ids
            ),
        )
        await db.execute(remove_query)
        return

    # if SRPM built we need to download them
    # from pulp repos in next tasks
    if srpm_artifact and build_task.built_srpm_url is None:
        srpm_url = "{}-src-{}-br/Packages/{}/{}".format(
            build_task.platform.name,
            build_task.build_id,
            srpm_artifact.name[0].lower(),
            srpm_artifact.name,
        )
        # we should update built_srpm_url for reusing SRPM
        # even if we don't have any uncompleted tasks
        update_query = (
            update(models.BuildTask)
            .where(
                models.BuildTask.ref_id == build_task.ref_id,
                models.BuildTask.platform_id == build_task.platform_id,
            )
            .values(
                built_srpm_url=srpm_url,
                alma_commit_cas_hash=request.alma_commit_cas_hash,
                is_cas_authenticated=request.is_cas_authenticated,
            )
        )
        await db.execute(update_query)
        if uncompleted_tasks_ids:
            insert_values = [
                {
                    "build_task_id": task_id,
                    "name": srpm_artifact.name,
                    "type": "rpm",
                    "cas_hash": srpm_artifact.cas_hash,
                    "href": srpm_artifact.href,
                }
                for task_id in uncompleted_tasks_ids
            ]
            await db.execute(insert(models.BuildTaskArtifact), insert_values)


async def fast_fail_other_tasks_by_ref(
    db: AsyncSession,
    current_task: models.BuildTask,
):
    build_tasks = await db.execute(
        select(models.BuildTask).where(
            models.BuildTask.id != current_task.id,
            models.BuildTask.ref_id == current_task.ref_id,
        )
    )
    build_tasks = build_tasks.scalars().all()
    uncompleted_tasks = [
        task for task in build_tasks if task.status == BuildTaskStatus.IDLE
    ]
    # if build_done raised exception in first arch of project,
    # we need to stop building the project and
    # fast-fail the uncompleted tasks
    if len(build_tasks) != len(uncompleted_tasks):
        return
    fast_fail_msg = (
        "Fast failed: build processing failed in the initial "
        f"architecture ({current_task.arch}). Please refer to the initial "
        "architecture build logs for more information about the failure."
    )
    uncompleted_tasks_ids = [task.id for task in uncompleted_tasks]
    await db.execute(
        update(models.BuildTask)
        .where(
            models.BuildTask.id.in_(uncompleted_tasks_ids),
        )
        .values(status=BuildTaskStatus.FAILED, error=fast_fail_msg)
    )
    await mark_dependent_tasks_queued(db, uncompleted_tasks_ids)
    await db.execute(
        delete(models.BuildTaskDependency).where(
            models.BuildTaskDependency.c.build_task_dependency.in_(
                uncompleted_tasks_ids
            ),
        )
    )


async def safe_build_done(
    db: AsyncSession,
    request: build_node_schema.BuildDone,
):
    success = True
    pulp = get_pulp_client()
    build_task_stats = {
        "build_node_stats": request.stats,
        "build_done_stats": {},
    }
    start_time = datetime.datetime.utcnow()
    logging.info("Start processing build_task: %d", request.task_id)
    try:
        async with pulp.begin():
            build_task, build_done_stats = await build_done(db, pulp, request)
            await db.flush()
    except Exception:
        logging.exception("Build done failed:")
        success = False
        build_task = await db.execute(
            select(models.BuildTask).where(
                models.BuildTask.id == request.task_id
            )
        )
        build_task = build_task.scalars().first()
        build_task.ts = datetime.datetime.utcnow()
        build_task.status = BuildTaskStatus.FAILED
        build_task.error = traceback.format_exc()
        await fast_fail_other_tasks_by_ref(db, build_task)
    else:
        end_time = datetime.datetime.utcnow()
        build_task_stats["build_done_stats"] = {
            "build_done": {
                "start_ts": str(start_time),
                "end_ts": str(end_time),
                "delta": str(end_time - start_time),
            },
            **build_done_stats,
        }
        await __update_built_srpm_url(db, build_task, request)
        await db.flush()
    finally:
        remove_dep_query = delete(models.BuildTaskDependency).where(
            models.BuildTaskDependency.c.build_task_dependency
            == request.task_id
        )
        build_task_start_time = request.stats.get("build_node_task", {}).get(
            "start_ts"
        )
        if build_task_start_time:
            build_task_start_time = datetime.datetime.fromisoformat(
                build_task_start_time
            )
        await db.execute(
            update(models.BuildTask)
            .where(models.BuildTask.id == request.task_id)
            .values(
                started_at=build_task_start_time,
                finished_at=datetime.datetime.utcnow(),
            )
        )
        await db.execute(
            insert(models.PerformanceStats).values(
                build_task_id=request.task_id,
                statistics=build_task_stats,
            ),
        )
        await mark_dependent_tasks_queued(db, [request.task_id])
        await db.execute(remove_dep_query)
        await db.flush()
    logging.info("Build task: %d, processing is finished", request.task_id)
    return success


async def build_done(
    db: AsyncSession,
    pulp: PulpClient,
    request: build_node_schema.BuildDone,
) -> typing.Tuple[models.BuildTask, typing.Dict[str, typing.Dict[str, str]]]:
    status = BuildTaskStatus.get_status_by_text(request.status)

    build_done_stats = {}
    build_task, processing_stats = await __process_build_task_artifacts(
        db,
        pulp,
        request.task_id,
        request.artifacts,
        status,
        request.git_commit_hash,
    )
    build_done_stats.update(processing_stats)

    await db.execute(
        update(models.BuildTask)
        .where(models.BuildTask.id == request.task_id)
        .values(status=status)
    )

    start_time = datetime.datetime.utcnow()
    binary_rpms = await save_noarch_packages(db, pulp, build_task)
    end_time = datetime.datetime.utcnow()
    processing_stats["noarch_processing"] = {
        "start_ts": str(start_time),
        "end_ts": str(end_time),
        "delta": str(end_time - start_time),
    }

    rpms_result = await db.execute(
        select(models.BuildTaskArtifact).where(
            models.BuildTaskArtifact.build_task_id == build_task.id,
            models.BuildTaskArtifact.type == "rpm",
        )
    )

    def get_srpm_instance(
        db_srpms: typing.List[models.SourceRpm],
        build_task: models.BuildTask,
        srpm_name: str = "",
    ) -> typing.Optional[models.SourceRpm]:
        srpm = None
        for db_srpm in db_srpms:
            if db_srpm.artifact.name == srpm_name:
                srpm = db_srpm
                break
            if (
                build_task.built_srpm_url
                and db_srpm.artifact.name in build_task.built_srpm_url
            ):
                srpm = db_srpm
                break
        return srpm

    srpm = None
    db_srpms = (
        (
            await db.execute(
                select(models.SourceRpm)
                .where(models.SourceRpm.build_id == build_task.build_id)
                .options(selectinload(models.SourceRpm.artifact))
            )
        )
        .scalars()
        .all()
    )

    for rpm in rpms_result.scalars().all():
        if rpm.name.endswith(".src.rpm"):
            # retrieve already created instance of model SourceRpm
            srpm = get_srpm_instance(db_srpms, build_task, rpm.name)
            if build_task.built_srpm_url is not None and srpm is not None:
                continue
        # if build task is excluded or failed, we don't need to create
        # SourceRpm and BinaryRpm records, because it breaks package releases
        if status in (BuildTaskStatus.EXCLUDED, BuildTaskStatus.FAILED):
            continue
        if rpm.name.endswith(".src.rpm") and srpm is None:
            srpm = models.SourceRpm()
            srpm.artifact = rpm
            srpm.build = build_task.build
        if not rpm.name.endswith(".src.rpm"):
            binary_rpm = models.BinaryRpm()
            binary_rpm.artifact = rpm
            binary_rpm.build = build_task.build
            binary_rpms.append(binary_rpm)

    # TODO: ALBS-705: Temporary solution that fixes integrity error with missing srpm,
    #       we need to investigate why src artifact sometimes is missing
    if not srpm:
        srpm = get_srpm_instance(db_srpms, build_task)
    if srpm:
        if build_task.built_srpm_url is None:
            db.add(srpm)
            await db.flush()
            await db.refresh(srpm)
        for binary_rpm in binary_rpms:
            binary_rpm.source_rpm = srpm

    db.add_all(binary_rpms)
    await db.flush()
    return build_task, build_done_stats

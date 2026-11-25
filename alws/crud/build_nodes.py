"""Build nodes registry.

Nodes register themselves: every ``ping``/``get_task`` request that carries
``node_name`` upserts the node row. This module also holds the queries
shared by the task dispatcher and the ``/build_nodes`` API.
"""

import datetime
import logging
import typing
from collections import defaultdict

import sqlalchemy
import sqlalchemy.orm
from pydantic import ValidationError
from sqlalchemy import func
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from alws import models
from alws.config import settings
from alws.constants import BuildTaskStatus
from alws.errors import DataNotFoundError
from alws.schemas import build_node_schema

__all__ = [
    'confirmed_dispatch_count',
    'count_active_tasks_by_node',
    'dispatchable_task_condition',
    'get_all_build_nodes',
    'get_build_node',
    'get_build_node_by_name',
    'get_build_nodes',
    'get_build_nodes_queue',
    'held_by_node_condition',
    'is_unconfirmed_claim',
    'register_build_node',
    'server_seen_since',
    'server_seen_since_query',
    'unconfirmed_claim_condition',
    'update_build_node',
]

# Tasks that aren't held by a node (claimed by nodes without node_name,
# or waiting for dramatiq after build_done) are handed out again when
# their ts is older than that. It's the logic used before the nodes registry.
LEGACY_TASK_TIMEOUT = datetime.timedelta(minutes=20)
RECENT_TASKS_LIMIT = 50
STATS_STATUSES = {
    BuildTaskStatus.COMPLETED: 'done',
    BuildTaskStatus.FAILED: 'failed',
    BuildTaskStatus.EXCLUDED: 'excluded',
}


def held_by_node_condition():
    """The task is being built on the node it was handed out to.

    Tasks reported via build_done stay STARTED until dramatiq processes
    the results, but they don't occupy a slot on the node anymore.
    """
    return sqlalchemy.and_(
        models.BuildTask.build_node_id.is_not(None),
        models.BuildTask.status == BuildTaskStatus.STARTED,
        models.BuildTask.node_reported_at.is_(None),
    )


def unconfirmed_claim_condition():
    """The task was handed out, but the node hasn't confirmed it got it.

    The claim sets ts to claimed_at, the ping of the node reporting the task
    and build_done change ts. So a node that never got the response to its
    get_task (it gave up waiting, the connection broke) leaves ts as it was.
    """
    return sqlalchemy.and_(
        models.BuildTask.status == BuildTaskStatus.STARTED,
        models.BuildTask.node_reported_at.is_(None),
        models.BuildTask.claimed_at.is_not(None),
        models.BuildTask.ts == models.BuildTask.claimed_at,
    )


def is_unconfirmed_claim(task: models.BuildTask) -> bool:
    """unconfirmed_claim_condition for a loaded task."""
    return (
        task.status == BuildTaskStatus.STARTED
        and task.node_reported_at is None
        and task.claimed_at is not None
        and task.ts == task.claimed_at
    )


def confirmed_dispatch_count():
    """dispatch_count after the node confirmed the task, for UPDATE ... SET.

    A handout is counted once, when it's confirmed: the confirmation changes
    ts, so the next one doesn't match unconfirmed_claim_condition anymore.
    Has to be set together with a new ts.
    """
    return models.BuildTask.dispatch_count + sqlalchemy.case(
        (unconfirmed_claim_condition(), 1),
        else_=0,
    )


def server_seen_since_query(now: datetime.datetime):
    """Since when the nodes saw the server working, as a scalar subquery.

    It's the earliest online_since of the nodes that are online now: such
    a node came all this time without a gap longer than
    BUILD_NODE_OFFLINE_TIMEOUT, so the server answered all this time. After
    a downtime of the server every node starts its online_since again, and
    there is no value while no node is online. It's kept in the database,
    so it's the same for every process of the server.
    """
    witness = sqlalchemy.orm.aliased(models.BuildNode)
    online_after = now - datetime.timedelta(
        seconds=settings.build_node_offline_timeout,
    )
    return (
        select(func.min(witness.online_since))
        .where(witness.last_seen > online_after)
        .scalar_subquery()
    )


async def server_seen_since(
    db: AsyncSession,
    now: datetime.datetime,
) -> typing.Optional[datetime.datetime]:
    """server_seen_since_query as a value, for BuildNode.is_silent_for."""
    return (await db.execute(select(server_seen_since_query(now)))).scalar()


def dispatchable_task_condition(now: datetime.datetime):
    """The task can be handed out to a node, dependencies aside.

    * a task held by a node becomes available again when the node
      wasn't seen for BUILD_NODE_TASK_RECLAIM_TIMEOUT while the server was
      working. A node that couldn't reach the server because the server
      was down isn't dead: its tasks are being built, and it gets the whole
      timeout to come back after the first node did (see
      server_seen_since_query);
    * any other unfinished task (idle, claimed by a node without
      ``node_name`` or already reported) keeps the old logic based on ``ts``.
    """
    reclaim_before = now - datetime.timedelta(
        seconds=settings.build_node_task_reclaim_timeout,
    )
    dead_nodes = select(models.BuildNode.id).where(
        sqlalchemy.or_(
            models.BuildNode.last_seen.is_(None),
            sqlalchemy.and_(
                models.BuildNode.last_seen < reclaim_before,
                server_seen_since_query(now) <= reclaim_before,
            ),
        )
    )
    return sqlalchemy.and_(
        models.BuildTask.status < BuildTaskStatus.COMPLETED,
        sqlalchemy.or_(
            sqlalchemy.and_(
                sqlalchemy.not_(held_by_node_condition()),
                sqlalchemy.or_(
                    models.BuildTask.ts.is_(None),
                    models.BuildTask.ts < now - LEGACY_TASK_TIMEOUT,
                ),
            ),
            sqlalchemy.and_(
                held_by_node_condition(),
                models.BuildTask.build_node_id.in_(dead_nodes),
            ),
        ),
    )


async def register_build_node(
    db: AsyncSession,
    name: str,
    now: datetime.datetime,
    node_info: typing.Optional[build_node_schema.NodeInfo] = None,
    resources: typing.Optional[build_node_schema.NodeResources] = None,
    supported_arches: typing.Optional[typing.List[str]] = None,
    excluded_packages: typing.Optional[typing.List[str]] = None,
    instance_id: typing.Optional[str] = None,
    instance_changed_at: typing.Optional[datetime.datetime] = None,
) -> models.BuildNode:
    """Create the node or refresh what it reported about itself.

    instance_changed_at is saved together with instance_id only.

    A known node is updated without INSERT: INSERT ... ON CONFLICT takes
    the next value of build_nodes_id_seq before it finds the conflict,
    so every ping and get_task of the node would spend one.
    """
    # A node coming back after it was offline starts a new period: it
    # doesn't know whether the server was working meanwhile
    offline_before = now - datetime.timedelta(
        seconds=settings.build_node_offline_timeout,
    )
    online_since = sqlalchemy.case(
        (
            sqlalchemy.or_(
                models.BuildNode.last_seen.is_(None),
                models.BuildNode.last_seen <= offline_before,
            ),
            now,
        ),
        else_=func.coalesce(models.BuildNode.online_since, now),
    )
    values = {'last_seen': now}
    if instance_id is not None:
        values.update(
            instance_id=instance_id,
            instance_changed_at=instance_changed_at,
        )
    if node_info is not None:
        values.update(
            version=node_info.version,
            capacity=node_info.capacity,
            node_type=node_info.node_type,
            pesign_support=node_info.pesign_support,
            maintenance=node_info.maintenance,
        )
        if node_info.supported_arches:
            supported_arches = node_info.supported_arches
    if supported_arches is not None:
        values['supported_arches'] = supported_arches
    if resources is not None:
        values.update(
            resources=resources.model_dump(),
            resources_updated_at=now,
        )
    if excluded_packages is not None:
        values['excluded_packages'] = excluded_packages
    result = await db.scalars(
        sqlalchemy.update(models.BuildNode)
        .where(models.BuildNode.name == name)
        .values(online_since=online_since, **values)
        .returning(models.BuildNode),
        execution_options={'populate_existing': True},
    )
    node = result.one_or_none()
    if node is not None:
        return node
    # The first registration. Another request of the node may insert it
    # concurrently, then the conflict turns this one into an update
    query = (
        pg_insert(models.BuildNode)
        .values(name=name, created_at=now, online_since=now, **values)
        .on_conflict_do_update(
            index_elements=[models.BuildNode.name],
            set_={'online_since': online_since, **values},
        )
        .returning(models.BuildNode)
    )
    result = await db.scalars(
        query,
        execution_options={'populate_existing': True},
    )
    return result.one()


async def get_build_node_by_name(
    db: AsyncSession,
    name: str,
    for_update: bool = False,
) -> typing.Optional[models.BuildNode]:
    query = (
        select(models.BuildNode)
        .where(models.BuildNode.name == name)
        .execution_options(populate_existing=True)
    )
    if for_update:
        query = query.with_for_update()
    result = await db.execute(query)
    return result.scalars().first()


async def get_all_build_nodes(
    db: AsyncSession,
) -> typing.List[models.BuildNode]:
    result = await db.execute(
        select(models.BuildNode)
        .order_by(models.BuildNode.name)
        .execution_options(populate_existing=True)
    )
    return list(result.scalars().all())


async def count_active_tasks_by_node(
    db: AsyncSession,
) -> typing.Dict[int, int]:
    result = await db.execute(
        select(models.BuildTask.build_node_id, func.count())
        .where(held_by_node_condition())
        .group_by(models.BuildTask.build_node_id)
    )
    return dict(result.all())


async def _get_active_tasks(
    db: AsyncSession,
    node_ids: typing.List[int],
) -> typing.Dict[int, typing.List[dict]]:
    tasks = defaultdict(list)
    if not node_ids:
        return tasks
    result = await db.execute(
        select(
            models.BuildTask.id,
            models.BuildTask.build_id,
            models.BuildTask.arch,
            models.BuildTask.claimed_at,
            models.BuildTask.build_node_id,
            models.BuildTask.dispatch_count,
            models.BuildTask.dispatch_nodes,
            models.BuildTaskRef.url,
        )
        .join(models.BuildTask.ref)
        .where(
            held_by_node_condition(),
            models.BuildTask.build_node_id.in_(node_ids),
        )
        .order_by(models.BuildTask.claimed_at, models.BuildTask.id)
    )
    for row in result.all():
        tasks[row.build_node_id].append({
            'id': row.id,
            'build_id': row.build_id,
            'arch': row.arch,
            'ref_url': row.url,
            'claimed_at': row.claimed_at,
            'dispatch_count': row.dispatch_count,
            'dispatch_nodes': row.dispatch_nodes or [],
        })
    return tasks


async def _get_stats_24h(
    db: AsyncSession,
    node_ids: typing.List[int],
    now: datetime.datetime,
) -> typing.Dict[int, typing.Dict[str, int]]:
    stats = defaultdict(lambda: {name: 0 for name in STATS_STATUSES.values()})
    if not node_ids:
        return stats
    result = await db.execute(
        select(
            models.BuildTask.build_node_id,
            models.BuildTask.status,
            func.count(),
        )
        .where(
            models.BuildTask.build_node_id.in_(node_ids),
            models.BuildTask.finished_at >= now - datetime.timedelta(hours=24),
            models.BuildTask.status.in_(list(STATS_STATUSES)),
        )
        .group_by(models.BuildTask.build_node_id, models.BuildTask.status)
    )
    for node_id, status, count in result.all():
        stats[node_id][STATS_STATUSES[status]] = count
    return stats


def _parse_resources(
    node: models.BuildNode,
) -> typing.Optional[build_node_schema.NodeResources]:
    if not node.resources:
        return None
    try:
        return build_node_schema.NodeResources.model_validate(node.resources)
    except ValidationError:
        logging.warning(
            'Build node %s has malformed resources: %s',
            node.name,
            node.resources,
        )
        return None


def _serialize_node(
    node: models.BuildNode,
    now: datetime.datetime,
    active_tasks: typing.List[dict],
    stats: typing.Dict[str, int],
) -> dict:
    return {
        'id': node.id,
        'name': node.name,
        'enabled': node.enabled,
        'drain': node.drain,
        'maintenance': node.maintenance,
        'online': node.is_online(now),
        'last_seen': node.last_seen,
        'version': node.version,
        'instance_id': node.instance_id,
        'supported_arches': node.supported_arches or [],
        'node_type': node.node_type,
        'pesign_support': node.pesign_support,
        'capacity': node.capacity,
        'capacity_override': node.capacity_override,
        'effective_capacity': node.effective_capacity,
        'active_tasks_count': len(active_tasks),
        'resources': _parse_resources(node),
        'resources_updated_at': node.resources_updated_at,
        'active_tasks': active_tasks,
        'stats_24h': stats,
    }


async def _serialize_nodes(
    db: AsyncSession,
    nodes: typing.List[models.BuildNode],
    now: datetime.datetime,
) -> typing.List[dict]:
    node_ids = [node.id for node in nodes]
    active_tasks = await _get_active_tasks(db, node_ids)
    stats = await _get_stats_24h(db, node_ids, now)
    return [
        _serialize_node(node, now, active_tasks[node.id], stats[node.id])
        for node in nodes
    ]


async def get_build_nodes(db: AsyncSession) -> typing.List[dict]:
    now = datetime.datetime.utcnow()
    nodes = await get_all_build_nodes(db)
    return await _serialize_nodes(db, nodes, now)


async def _get_node_or_raise(
    db: AsyncSession,
    node_id: int,
) -> models.BuildNode:
    result = await db.execute(
        select(models.BuildNode)
        .where(models.BuildNode.id == node_id)
        .execution_options(populate_existing=True)
    )
    node = result.scalars().first()
    if node is None:
        raise DataNotFoundError(f'Build node with id={node_id} is not found')
    return node


async def _get_recent_tasks(
    db: AsyncSession,
    node_id: int,
) -> typing.List[dict]:
    result = await db.execute(
        select(
            models.BuildTask.id,
            models.BuildTask.build_id,
            models.BuildTask.arch,
            models.BuildTask.status,
            models.BuildTask.claimed_at,
            models.BuildTask.finished_at,
            models.BuildTask.dispatch_count,
            models.BuildTask.dispatch_nodes,
            models.BuildTaskRef.url,
        )
        .join(models.BuildTask.ref)
        .where(models.BuildTask.build_node_id == node_id)
        .order_by(
            models.BuildTask.claimed_at.desc().nulls_last(),
            models.BuildTask.id.desc(),
        )
        .limit(RECENT_TASKS_LIMIT)
    )
    return [
        {
            'id': row.id,
            'build_id': row.build_id,
            'arch': row.arch,
            'ref_url': row.url,
            'status': row.status,
            'claimed_at': row.claimed_at,
            'finished_at': row.finished_at,
            'dispatch_count': row.dispatch_count,
            'dispatch_nodes': row.dispatch_nodes or [],
        }
        for row in result.all()
    ]


async def get_build_node(db: AsyncSession, node_id: int) -> dict:
    now = datetime.datetime.utcnow()
    node = await _get_node_or_raise(db, node_id)
    serialized = (await _serialize_nodes(db, [node], now))[0]
    serialized['recent_tasks'] = await _get_recent_tasks(db, node_id)
    return serialized


async def update_build_node(
    db: AsyncSession,
    node_id: int,
    payload: build_node_schema.BuildNodeUpdate,
) -> dict:
    node = await _get_node_or_raise(db, node_id)
    # capacity_override=null resets the limit, so only the fields
    # that were actually sent are applied
    for field, value in payload.model_dump(exclude_unset=True).items():
        if field in ('enabled', 'drain') and value is None:
            continue
        setattr(node, field, value)
    await db.flush()
    now = datetime.datetime.utcnow()
    return (await _serialize_nodes(db, [node], now))[0]


async def get_build_nodes_queue(db: AsyncSession) -> typing.List[dict]:
    now = datetime.datetime.utcnow()
    dispatchable = dispatchable_task_condition(now)
    queued = await db.execute(
        select(models.BuildTask.arch, func.count())
        .where(~models.BuildTask.dependencies.any(), dispatchable)
        .group_by(models.BuildTask.arch)
    )
    queued = dict(queued.all())
    # STARTED tasks that are really being built somewhere: held by
    # a live node or claimed by a node without node_name and not expired
    active = await db.execute(
        select(models.BuildTask.arch, func.count())
        .where(
            models.BuildTask.status == BuildTaskStatus.STARTED,
            models.BuildTask.node_reported_at.is_(None),
            sqlalchemy.not_(dispatchable),
        )
        .group_by(models.BuildTask.arch)
    )
    active = dict(active.all())
    online_nodes = defaultdict(int)
    total_capacity = defaultdict(int)
    accepting_node_ids = []
    for node in await get_all_build_nodes(db):
        if not node.is_online(now) or not node.accepts_tasks():
            continue
        accepting_node_ids.append(node.id)
        for arch in node.supported_arches or []:
            online_nodes[arch] += 1
            total_capacity[arch] += node.effective_capacity
    # The part of active_tasks comparable with total_capacity: the tasks
    # held by the nodes counted in online_nodes
    accepting_active = {}
    if accepting_node_ids:
        accepting_active = await db.execute(
            select(models.BuildTask.arch, func.count())
            .where(
                held_by_node_condition(),
                models.BuildTask.build_node_id.in_(accepting_node_ids),
            )
            .group_by(models.BuildTask.arch)
        )
        accepting_active = dict(accepting_active.all())
    # Tasks being built by the nodes without node_name
    unregistered_active = await db.execute(
        select(models.BuildTask.arch, func.count())
        .where(
            models.BuildTask.status == BuildTaskStatus.STARTED,
            models.BuildTask.node_reported_at.is_(None),
            models.BuildTask.build_node_id.is_(None),
            models.BuildTask.ts >= now - LEGACY_TASK_TIMEOUT,
        )
        .group_by(models.BuildTask.arch)
    )
    unregistered_active = dict(unregistered_active.all())
    arches = sorted(
        set(queued)
        | set(active)
        | set(online_nodes)
        | set(accepting_active)
        | set(unregistered_active)
    )
    return [
        {
            'arch': arch,
            'queued_tasks': queued.get(arch, 0),
            'online_nodes': online_nodes.get(arch, 0),
            'total_capacity': total_capacity.get(arch, 0),
            'active_tasks': active.get(arch, 0),
            'accepting_active_tasks': accepting_active.get(arch, 0),
            'unregistered_active_tasks': unregistered_active.get(arch, 0),
        }
        for arch in arches
    ]

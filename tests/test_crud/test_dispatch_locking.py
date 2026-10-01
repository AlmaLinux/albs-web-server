"""Concurrency behaviour of the three task-dispatch queries.

``get_available_build_task``, ``get_available_test_tasks`` and
``get_available_sign_task`` are queue pops: several nodes poll them at the
same time and each one has to walk away with a different task. That needs
``LIMIT`` (so a poller locks one task rather than every eligible task) and
``SKIP LOCKED`` (so a second poller steps over the row the first one is
claiming instead of blocking on it).

Neither property is observable from a single session, so these tests drive
two independent connections. They also bound every dispatch call with
``asyncio.wait_for``: a regression that drops ``SKIP LOCKED`` makes the
second poller block until the first transaction ends, which would otherwise
hang the suite instead of failing it.
"""

import asyncio
import datetime
import os
import uuid

import pytest
from sqlalchemy import select
from sqlalchemy.dialects import postgresql
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from alws import models
from alws.config import settings
from alws.constants import BuildTaskStatus, SignStatus
from alws.constants import TestTaskStatus as TestStatus
from alws.crud.build_node import get_available_build_task
from alws.crud.sign_task import get_available_sign_task
from alws.crud.test import get_available_test_tasks
from alws.schemas import build_node_schema
from tests.constants import ADMIN_USER_ID

pytestmark = pytest.mark.anyio

# A poller that has to wait for another poller's transaction is the bug
# these tests are about, so anything slower than this counts as blocked.
DISPATCH_TIMEOUT = 15


@pytest.fixture
async def session_factory():
    """Sessions on connections of their own, so row locks are observable.

    The shared ``async_session`` fixture hands every caller the same
    connection, where one statement can never block on another's lock.
    """
    engine = create_async_engine(
        os.getenv(
            "DATABASE_URL",
            settings.fastapi_sqla__async__sqlalchemy_url,
        ),
        poolclass=NullPool,
    )
    factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        yield factory
    finally:
        await engine.dispose()


async def _seed_platform_and_build(session):
    suffix = uuid.uuid4().hex[:8]
    platform = models.Platform(
        name=f"dispatch-lock-{suffix}",
        type="rpm",
        distr_type="rhel",
        distr_version="9",
        test_dist_name="almalinux",
        arch_list=["x86_64"],
        data={},
        modularity={},
    )
    session.add(platform)
    await session.flush()
    build = models.Build(owner_id=ADMIN_USER_ID, mock_options={})
    session.add(build)
    await session.flush()
    ref = models.BuildTaskRef(
        url=f"https://git.almalinux.org/rpms/dispatch-{suffix}.git",
        git_ref="a1",
        ref_type=4,
    )
    session.add(ref)
    await session.flush()
    return platform, build, ref


@pytest.fixture
async def idle_build_tasks(session_factory):
    """Five claimable build tasks, committed so other sessions can see them."""
    async with session_factory() as session:
        platform, build, ref = await _seed_platform_and_build(session)
        tasks = [
            models.BuildTask(
                build_id=build.id,
                platform_id=platform.id,
                ref_id=ref.id,
                status=BuildTaskStatus.IDLE,
                index=0,
                arch="x86_64",
                mock_options={},
            )
            for _ in range(5)
        ]
        session.add_all(tasks)
        await session.commit()
        return [task.id for task in tasks]


@pytest.fixture
async def created_test_tasks(session_factory):
    """Fifteen CREATED test tasks - more than the batch size of ten."""
    async with session_factory() as session:
        platform, build, ref = await _seed_platform_and_build(session)
        build_task = models.BuildTask(
            build_id=build.id,
            platform_id=platform.id,
            ref_id=ref.id,
            status=BuildTaskStatus.COMPLETED,
            index=0,
            arch="x86_64",
            mock_options={},
        )
        session.add(build_task)
        await session.flush()
        tasks = [
            models.TestTask(
                build_task_id=build_task.id,
                package_name=f"pkg-{number}",
                package_version="1.0",
                package_release="1.el9",
                env_arch="x86_64",
                status=TestStatus.CREATED,
                revision=1,
            )
            for number in range(15)
        ]
        session.add_all(tasks)
        await session.commit()
        return [task.id for task in tasks]


@pytest.fixture
async def idle_sign_tasks(session_factory):
    """Two idle sign tasks sharing one key, committed."""
    async with session_factory() as session:
        _, build, _ = await _seed_platform_and_build(session)
        suffix = uuid.uuid4().hex[:8]
        sign_key = models.SignKey(
            name=f"dispatch-lock-key-{suffix}",
            keyid=uuid.uuid4().hex[:16],
            fingerprint=uuid.uuid4().hex[:40],
            public_url=f"http://example.com/{suffix}",
        )
        session.add(sign_key)
        await session.flush()
        tasks = [
            models.SignTask(
                build_id=build.id,
                sign_key_id=sign_key.id,
                status=SignStatus.IDLE,
                ts=datetime.datetime.utcnow() - datetime.timedelta(hours=1),
            )
            for _ in range(2)
        ]
        session.add_all(tasks)
        await session.commit()
        return sign_key.keyid, [task.id for task in tasks]


class TestBuildTaskDispatch:
    async def test_locks_only_the_claimed_task(
        self,
        session_factory,
        idle_build_tasks,
    ):
        """One poller must leave the other tasks claimable.

        Without ``LIMIT 1`` the statement returns every eligible task and
        ``FOR UPDATE`` locks all of them, so a second poller finds nothing
        free even though only one task was actually handed out.
        """
        request = build_node_schema.RequestTask(supported_arches=["x86_64"])
        async with session_factory() as claimer, session_factory() as probe:
            claimed = await asyncio.wait_for(
                get_available_build_task(claimer, request),
                timeout=DISPATCH_TIMEOUT,
            )
            assert claimed is not None, "Nothing was handed out"

            # Everything the claimer did not take is still lockable.
            still_free = (
                (
                    await probe.execute(
                        select(models.BuildTask.id)
                        .where(models.BuildTask.id.in_(idle_build_tasks))
                        .with_for_update(skip_locked=True)
                    )
                )
                .scalars()
                .all()
            )
            assert claimed.id not in still_free, "Claimed task is not locked"
            message = (
                f"Expected {len(idle_build_tasks) - 1} tasks to stay "
                f"claimable, got {len(still_free)}. The dispatch query is "
                "locking more rows than it hands out."
            )
            assert len(still_free) == len(idle_build_tasks) - 1, message
            await probe.rollback()
            await claimer.rollback()

    async def test_second_poller_gets_a_different_task(
        self,
        session_factory,
        idle_build_tasks,
    ):
        """Two nodes polling at once get two different tasks, without waiting.

        Without ``SKIP LOCKED`` the second call blocks on the row the first
        one is claiming until that transaction ends, which is what caps
        dispatch throughput under contention.
        """
        request = build_node_schema.RequestTask(supported_arches=["x86_64"])
        async with session_factory() as first, session_factory() as second:
            first_task = await asyncio.wait_for(
                get_available_build_task(first, request),
                timeout=DISPATCH_TIMEOUT,
            )
            try:
                second_task = await asyncio.wait_for(
                    get_available_build_task(second, request),
                    timeout=DISPATCH_TIMEOUT,
                )
            except asyncio.TimeoutError:
                pytest.fail(
                    "Second poller blocked on the first poller's lock - "
                    "SKIP LOCKED is missing from the dispatch query"
                )
            assert first_task is not None and second_task is not None
            message = "Both pollers were handed the same build task"
            assert first_task.id != second_task.id, message
            await first.rollback()
            await second.rollback()

    async def test_query_shape(self):
        """Guard the two clauses the behaviour above depends on."""
        request = build_node_schema.RequestTask(supported_arches=["x86_64"])

        class _Recorder:
            statement = None

            async def execute(self, statement):
                type(self).statement = statement
                raise _Stop()

        class _Stop(Exception):
            pass

        recorder = _Recorder()
        with pytest.raises(_Stop):
            await get_available_build_task(recorder, request)

        sql = " ".join(
            str(
                _Recorder.statement.compile(dialect=postgresql.dialect())
            ).split()
        )
        assert "FOR UPDATE OF build_tasks SKIP LOCKED" in sql, sql
        assert "LIMIT" in sql, sql


class TestTestTaskDispatch:
    async def test_second_scheduler_gets_a_different_batch(
        self,
        session_factory,
        created_test_tasks,
    ):
        """Two ALTS schedulers polling at once take disjoint batches."""
        async with session_factory() as first, session_factory() as second:
            first_batch = await asyncio.wait_for(
                get_available_test_tasks(first),
                timeout=DISPATCH_TIMEOUT,
            )
            try:
                second_batch = await asyncio.wait_for(
                    get_available_test_tasks(second),
                    timeout=DISPATCH_TIMEOUT,
                )
            except asyncio.TimeoutError:
                pytest.fail(
                    "Second scheduler blocked on the first one's batch - "
                    "SKIP LOCKED is missing from the dispatch query"
                )

            first_ids = {payload["bs_task_id"] for payload in first_batch}
            second_ids = {payload["bs_task_id"] for payload in second_batch}
            assert len(first_ids) == 10, "First batch is not a full batch"
            assert second_ids, "Second scheduler got nothing to run"
            message = "Both schedulers were handed the same test tasks"
            assert not first_ids & second_ids, message
            await first.rollback()
            await second.rollback()


class TestSignTaskDispatch:
    async def test_claim_is_exclusive(
        self,
        session_factory,
        idle_sign_tasks,
    ):
        """Two sign nodes polling at once must not claim the same task.

        The old query read the task without a lock and then updated it
        unconditionally, so both nodes could walk away with the same one.
        Each session sees only its own uncommitted claim, which is what makes
        the two IN_PROGRESS sets comparable here.
        """
        keyid, task_ids = idle_sign_tasks
        async with session_factory() as first, session_factory() as second:
            await asyncio.wait_for(
                get_available_sign_task(first, [keyid]),
                timeout=DISPATCH_TIMEOUT,
            )
            try:
                await asyncio.wait_for(
                    get_available_sign_task(second, [keyid]),
                    timeout=DISPATCH_TIMEOUT,
                )
            except asyncio.TimeoutError:
                pytest.fail(
                    "Second sign node blocked on the first one's lock - "
                    "SKIP LOCKED is missing from the dispatch query"
                )

            claims = []
            for session in (first, second):
                claimed = (
                    (
                        await session.execute(
                            select(models.SignTask.id).where(
                                models.SignTask.id.in_(task_ids),
                                models.SignTask.status
                                == SignStatus.IN_PROGRESS,
                            )
                        )
                    )
                    .scalars()
                    .all()
                )
                claims.append(set(claimed))

            assert all(len(claim) == 1 for claim in claims), (
                f"Each node should claim exactly one task, got {claims}"
            )
            message = "Both sign nodes claimed the same task"
            assert not claims[0] & claims[1], message
            await first.rollback()
            await second.rollback()

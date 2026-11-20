"""Build nodes registry, balanced dispatch and the /build_nodes API.

Every test works with an architecture of its own, so the tasks and the nodes
left by the other tests of the module can't take part in its dispatch.
"""

import asyncio
import datetime
import os
import time
import typing
import uuid

import jwt
import pytest
from sqlalchemy import func, select, text, update
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from alws import auth, models
from alws.config import settings
from alws.constants import BuildTaskStatus
from alws.crud import build_node as build_node_crud
from alws.crud import build_nodes as build_nodes_crud
from alws.dramatiq.build import _build_done
from alws.schemas.build_node_schema import BuildDone
from scripts import build_node_token
from tests.constants import ADMIN_USER_ID, CUSTOM_USER_ID
from tests.mock_classes import BaseAsyncTestCase

RESOURCES = {
    "cpu_count": 16,
    "load_avg": [1.5, 1.25, 1.0],
    "mem_total_bytes": 64 * 1024**3,
    "mem_available_bytes": 32 * 1024**3,
    "disk_path": "/srv/alternatives",
    "disk_total_bytes": 1024**4,
    "disk_free_bytes": 512 * 1024**3,
}


@pytest.fixture
async def session_factory():
    """Sessions on connections of their own, committing like the app does."""
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


@pytest.fixture
def arch() -> str:
    return f"bn-{uuid.uuid4().hex[:8]}"


def node_name() -> str:
    return f"node-{uuid.uuid4().hex[:8]}"


@pytest.fixture
def seed_tasks(session_factory, arch):
    """Create ready-to-build tasks of the test architecture."""

    async def _seed(
        count: int,
        is_secure_boot: bool = False,
        queued_at: typing.Optional[datetime.datetime] = None,
    ) -> typing.List[int]:
        suffix = uuid.uuid4().hex[:8]
        async with session_factory() as session:
            platform = models.Platform(
                name=f"build-nodes-{suffix}",
                type="rpm",
                distr_type="rhel",
                distr_version="9",
                test_dist_name="almalinux",
                arch_list=[arch],
                data={"mock": {}, "definitions": {}, "yum": {}},
                modularity={},
            )
            build = models.Build(owner_id=ADMIN_USER_ID, mock_options={})
            ref = models.BuildTaskRef(
                url=f"https://git.almalinux.org/rpms/bn-{suffix}.git",
                git_ref="a1",
                ref_type=4,
            )
            session.add_all([platform, build, ref])
            await session.flush()
            tasks = [
                models.BuildTask(
                    build_id=build.id,
                    platform_id=platform.id,
                    ref_id=ref.id,
                    status=BuildTaskStatus.IDLE,
                    index=index,
                    arch=arch,
                    is_secure_boot=is_secure_boot,
                    mock_options={},
                    queued_at=queued_at or datetime.datetime.utcnow(),
                )
                for index in range(count)
            ]
            session.add_all(tasks)
            await session.commit()
            return [task.id for task in tasks]

    return _seed


class BuildNodesTestCase(BaseAsyncTestCase):
    @staticmethod
    def node_info(
        arch: str,
        capacity: int = 8,
        pesign: bool = False,
        maintenance: bool = False,
        instance_id: typing.Optional[str] = None,
        previous_instance_id: typing.Optional[str] = None,
    ) -> dict:
        info = {
            "version": "1.0.0",
            "supported_arches": [arch],
            "capacity": capacity,
            "node_type": "x86_64",
            "pesign_support": pesign,
            "maintenance": maintenance,
        }
        if instance_id is not None:
            info["instance_id"] = instance_id
        if previous_instance_id is not None:
            info["previous_instance_id"] = previous_instance_id
        return info

    async def get_task(
        self,
        name: typing.Optional[str],
        arch: str,
        **node_info,
    ) -> typing.Optional[int]:
        payload = {"supported_arches": [arch], "excluded_packages": []}
        if name:
            payload["node_name"] = name
            payload["node_info"] = self.node_info(arch, **node_info)
        response = await self.make_request(
            "post",
            "/api/v1/build_node/get_task",
            json=payload,
        )
        message = f"Cannot get task:\n{response.text}"
        assert response.status_code == self.status_codes.HTTP_200_OK, message
        task = response.json()
        return task["id"] if task else None

    async def ping(
        self,
        name: str,
        arch: str,
        active_tasks: typing.List[int] = (),
        **node_info,
    ):
        response = await self.make_request(
            "post",
            "/api/v1/build_node/ping",
            json={
                "active_tasks": list(active_tasks),
                "node_name": name,
                "node_info": self.node_info(arch, **node_info),
                "resources": RESOURCES,
            },
        )
        message = f"Cannot ping:\n{response.text}"
        assert response.status_code == self.status_codes.HTTP_200_OK, message

    async def build_done(self, task_id: int, name: typing.Optional[str]):
        payload = {
            "task_id": task_id,
            "status": "done",
            "artifacts": [],
            "stats": {},
        }
        if name:
            payload["node_name"] = name
        return await self.make_request(
            "post",
            "/api/v1/build_node/build_done",
            json=payload,
        )

    async def drain_queue(
        self,
        arch: str,
        nodes: typing.Dict[str, int],
        order: typing.List[str],
    ) -> typing.Dict[str, typing.List[int]]:
        """Poll the nodes in the given order, return what each one got."""
        got = {name: [] for name in nodes}
        for name in order:
            task_id = await self.get_task(name, arch, capacity=nodes[name])
            if task_id:
                got[name].append(task_id)
        return got

    async def request_as(self, token, method, endpoint, payload):
        """Make the request with the given token or without any."""
        old_token = self.headers.pop("Authorization", None)
        headers = {}
        if token is not None:
            headers["Authorization"] = f"Bearer {token}"
        kwargs = {"headers": headers}
        if payload is not None:
            kwargs["json"] = payload
        try:
            return await self.make_request(method, endpoint, **kwargs)
        finally:
            self.headers["Authorization"] = old_token

    @staticmethod
    async def get_db_task(session_factory, task_id: int) -> models.BuildTask:
        async with session_factory() as session:
            return await session.get(models.BuildTask, task_id)

    @staticmethod
    async def get_db_node(session_factory, name: str) -> models.BuildNode:
        async with session_factory() as session:
            return (
                await session.execute(
                    select(models.BuildNode).where(
                        models.BuildNode.name == name
                    )
                )
            ).scalar_one()

    @staticmethod
    async def update_tasks(session_factory, task_ids, **values):
        async with session_factory() as session:
            await session.execute(
                update(models.BuildTask)
                .where(models.BuildTask.id.in_(task_ids))
                .values(**values)
            )
            await session.commit()

    @staticmethod
    async def update_node(session_factory, name: str, **values):
        async with session_factory() as session:
            await session.execute(
                update(models.BuildNode)
                .where(models.BuildNode.name == name)
                .values(**values)
            )
            await session.commit()


class TestBuildNodesBalancing(BuildNodesTestCase):
    @pytest.mark.parametrize(
        "order",
        [
            ["a"] * 8 + ["b"] * 8,
            ["a", "b"] * 8,
            ["b", "a", "a", "b", "a", "a", "a", "b", "b", "b", "a", "b"],
        ],
        ids=["one-after-another", "interleaved", "mixed"],
    )
    async def test_equal_nodes_share_tasks_evenly(
        self,
        arch,
        seed_tasks,
        order,
    ):
        await seed_tasks(6)
        names = {"a": node_name(), "b": node_name()}
        nodes = {names["a"]: 8, names["b"]: 8}
        for name in nodes:
            await self.ping(name, arch)
        got = await self.drain_queue(arch, nodes, [names[key] for key in order])
        counts = sorted(len(tasks) for tasks in got.values())
        message = f"Tasks are not split evenly: {got}"
        assert sum(counts) == 6, message
        assert counts[1] - counts[0] <= 1, message

    @pytest.mark.parametrize("first", ["big", "small"])
    async def test_share_follows_capacity(self, arch, seed_tasks, first):
        await seed_tasks(6)
        big, small = node_name(), node_name()
        nodes = {big: 8, small: 4}
        await self.ping(big, arch, capacity=8)
        await self.ping(small, arch, capacity=4)
        order = [big] * 8 + [small] * 8
        if first == "small":
            order.reverse()
        got = await self.drain_queue(arch, nodes, order)
        message = f"Tasks are not split as 4/2: {got}"
        assert len(got[big]) + len(got[small]) == 6, message
        assert abs(len(got[big]) - 4) <= 1, message
        assert abs(len(got[small]) - 2) <= 1, message

    async def test_long_queue_fills_every_slot(self, arch, seed_tasks):
        await seed_tasks(20)
        first, second = node_name(), node_name()
        nodes = {first: 8, second: 8}
        for name in nodes:
            await self.ping(name, arch)
        got = await self.drain_queue(arch, nodes, [first, second] * 12)
        message = f"Nodes are not filled up: {got}"
        assert len(got[first]) == 8, message
        assert len(got[second]) == 8, message

    async def test_node_never_exceeds_effective_capacity(
        self,
        arch,
        seed_tasks,
        session_factory,
    ):
        await seed_tasks(5)
        name = node_name()
        got = await self.drain_queue(arch, {name: 2}, [name] * 4)
        assert len(got[name]) == 2, f"Node capacity is ignored: {got}"
        # A free slot, but the admin limit is lower than the node capacity
        await self.update_tasks(
            session_factory,
            got[name][:1],
            status=BuildTaskStatus.COMPLETED,
        )
        await self.update_node(session_factory, name, capacity_override=1)
        assert await self.get_task(name, arch, capacity=2) is None
        await self.update_node(session_factory, name, capacity_override=None)
        assert await self.get_task(name, arch, capacity=2) is not None
        assert await self.get_task(name, arch, capacity=2) is None

    @pytest.mark.parametrize(
        "node_state",
        [
            {"enabled": False},
            {"drain": True},
            {"maintenance": True},
        ],
        ids=["disabled", "drain", "maintenance"],
    )
    async def test_unavailable_node_gets_nothing(
        self,
        arch,
        seed_tasks,
        session_factory,
        node_state,
    ):
        task_ids = await seed_tasks(2)
        name = node_name()
        maintenance = node_state.get("maintenance", False)
        await self.ping(name, arch, maintenance=maintenance)
        if not maintenance:
            await self.update_node(session_factory, name, **node_state)
        task_id = await self.get_task(name, arch, maintenance=maintenance)
        assert task_id is None, f"Node in {node_state} got a task"
        task = await self.get_db_task(session_factory, task_ids[0])
        assert task.status == BuildTaskStatus.IDLE

    async def test_secure_boot_task_goes_to_pesign_node(
        self,
        arch,
        seed_tasks,
    ):
        (task_id,) = await seed_tasks(1, is_secure_boot=True)
        plain, pesign = node_name(), node_name()
        await self.ping(plain, arch)
        await self.ping(pesign, arch, pesign=True)
        assert await self.get_task(plain, arch) is None
        assert await self.get_task(pesign, arch, pesign=True) == task_id

    async def test_starving_task_goes_over_the_share(
        self,
        arch,
        seed_tasks,
        session_factory,
    ):
        task_ids = await seed_tasks(2)
        busy, idle = node_name(), node_name()
        await self.ping(busy, arch)
        await self.ping(idle, arch)
        # share = ceil(8 * 2 / 16) = 1
        assert await self.get_task(busy, arch) == task_ids[0]
        assert await self.get_task(busy, arch) is None
        waited = settings.build_node_balancer_max_wait + 5
        await self.update_tasks(
            session_factory,
            task_ids[1:],
            queued_at=datetime.datetime.utcnow()
            - datetime.timedelta(seconds=waited),
        )
        assert await self.get_task(busy, arch) == task_ids[1]

    @pytest.mark.parametrize("late_task", ["secure-boot", "starving"])
    async def test_task_beyond_the_first_candidates_page(
        self,
        arch,
        seed_tasks,
        monkeypatch,
        late_task,
    ):
        """The node at its share for the oldest tasks gets a later one."""
        monkeypatch.setattr(build_node_crud, "BALANCER_CANDIDATES_LIMIT", 2)
        plain_ids = await seed_tasks(5)
        if late_task == "secure-boot":
            # Only this node can build it
            (late_id,) = await seed_tasks(1, is_secure_boot=True)
        else:
            waited = settings.build_node_balancer_max_wait + 5
            (late_id,) = await seed_tasks(
                1,
                queued_at=datetime.datetime.utcnow()
                - datetime.timedelta(seconds=waited),
            )
        name, other = node_name(), node_name()
        await self.ping(name, arch, pesign=True)
        await self.ping(other, arch)
        # share = ceil(8 * 6 / 16) = 3 for the plain tasks
        for task_id in plain_ids[:3]:
            assert await self.get_task(name, arch, pesign=True) == task_id
        # The node is at its share for every task of the first page
        assert await self.get_task(name, arch, pesign=True) == late_id
        assert await self.get_task(name, arch, pesign=True) is None

    async def test_claim_binds_task_to_node(
        self,
        arch,
        seed_tasks,
        session_factory,
    ):
        (task_id,) = await seed_tasks(1)
        name = node_name()
        assert await self.get_task(name, arch) == task_id
        task = await self.get_db_task(session_factory, task_id)
        node = await self.get_db_node(session_factory, name)
        assert task.status == BuildTaskStatus.STARTED
        assert task.build_node_id == node.id
        assert task.claimed_at is not None
        assert task.ts is not None
        assert node.supported_arches == [arch]
        assert node.excluded_packages == []

    async def test_requests_without_node_name(
        self,
        arch,
        seed_tasks,
        session_factory,
    ):
        """Old nodes get the oldest task, secure boot or not, as before."""
        task_ids = await seed_tasks(2, is_secure_boot=True)
        response = await self.make_request(
            "post",
            "/api/v1/build_node/get_task",
            json={"supported_arches": [arch], "excluded_packages": []},
        )
        assert response.status_code == self.status_codes.HTTP_200_OK
        assert response.json()["id"] == task_ids[0]
        task = await self.get_db_task(session_factory, task_ids[0])
        assert task.status == BuildTaskStatus.STARTED
        assert task.build_node_id is None
        ts = task.ts

        response = await self.make_request(
            "post",
            "/api/v1/build_node/ping",
            json={"active_tasks": [task_ids[0]]},
        )
        assert response.status_code == self.status_codes.HTTP_200_OK
        task = await self.get_db_task(session_factory, task_ids[0])
        assert task.ts > ts, "ts of the task is not refreshed by the ping"

        assert await self.get_task(None, arch) == task_ids[1]
        assert await self.get_task(None, arch) is None


class TestBuildNodesReconciliation(BuildNodesTestCase):
    async def test_ping_returns_lost_tasks(
        self,
        arch,
        seed_tasks,
        session_factory,
    ):
        task_ids = await seed_tasks(3)
        name = node_name()
        got = [await self.get_task(name, arch) for _ in task_ids]
        assert got == task_ids
        claimed_at = datetime.datetime.utcnow() - datetime.timedelta(
            seconds=settings.build_node_reconcile_grace + 30,
        )
        # The last task was handed out just now, it may be not in the ping
        await self.update_tasks(
            session_factory,
            task_ids[:2],
            claimed_at=claimed_at,
            ts=claimed_at,
        )
        await self.ping(name, arch, active_tasks=[task_ids[0]])

        kept = await self.get_db_task(session_factory, task_ids[0])
        assert kept.status == BuildTaskStatus.STARTED
        assert kept.ts > claimed_at, "ts of the reported task is not updated"
        lost = await self.get_db_task(session_factory, task_ids[1])
        assert lost.status == BuildTaskStatus.IDLE
        assert lost.build_node_id is None
        assert lost.ts is None
        fresh = await self.get_db_task(session_factory, task_ids[2])
        assert fresh.status == BuildTaskStatus.STARTED
        assert fresh.build_node_id == kept.build_node_id

        # The returned task can be handed out again
        assert await self.get_task(node_name(), arch) == task_ids[1]

    async def test_ping_refreshes_only_own_tasks(
        self,
        arch,
        seed_tasks,
        session_factory,
    ):
        (task_id,) = await seed_tasks(1)
        owner, other = node_name(), node_name()
        assert await self.get_task(owner, arch) == task_id
        old_ts = datetime.datetime.utcnow() - datetime.timedelta(minutes=5)
        await self.update_tasks(session_factory, [task_id], ts=old_ts)
        await self.ping(other, arch, active_tasks=[task_id])
        task = await self.get_db_task(session_factory, task_id)
        assert task.ts == old_ts, "Another node refreshed the task"

    async def test_tasks_of_dead_node_are_reclaimed(
        self,
        arch,
        seed_tasks,
        session_factory,
    ):
        (task_id,) = await seed_tasks(1)
        dead, alive = node_name(), node_name()
        assert await self.get_task(dead, arch) == task_id
        assert await self.get_task(alive, arch) is None
        last_seen = datetime.datetime.utcnow() - datetime.timedelta(
            seconds=settings.build_node_task_reclaim_timeout + 10,
        )
        await self.update_node(session_factory, dead, last_seen=last_seen)
        assert await self.get_task(alive, arch) == task_id
        task = await self.get_db_task(session_factory, task_id)
        alive_node = await self.get_db_node(session_factory, alive)
        assert task.build_node_id == alive_node.id

        # The dead node is back and reports the results: they are refused
        response = await self.build_done(task_id, dead)
        assert response.status_code == self.status_codes.HTTP_409_CONFLICT
        response = await self.build_done(task_id, alive)
        assert response.status_code == self.status_codes.HTTP_200_OK

    async def test_reported_task_is_not_returned(
        self,
        arch,
        seed_tasks,
        session_factory,
    ):
        task_ids = await seed_tasks(2)
        name = node_name()
        assert await self.get_task(name, arch, capacity=1) == task_ids[0]
        assert await self.get_task(name, arch, capacity=1) is None

        response = await self.build_done(task_ids[0], name)
        assert response.status_code == self.status_codes.HTTP_200_OK
        task = await self.get_db_task(session_factory, task_ids[0])
        assert task.node_reported_at is not None
        assert task.ts > datetime.datetime.utcnow() + datetime.timedelta(
            hours=2
        )

        # The reported task doesn't occupy the only slot of the node anymore
        assert await self.get_task(name, arch, capacity=1) == task_ids[1]

        claimed_at = datetime.datetime.utcnow() - datetime.timedelta(
            seconds=settings.build_node_reconcile_grace + 30,
        )
        await self.update_tasks(
            session_factory,
            [task_ids[0]],
            claimed_at=claimed_at,
        )
        await self.ping(name, arch, active_tasks=[task_ids[1]])
        task = await self.get_db_task(session_factory, task_ids[0])
        assert task.status == BuildTaskStatus.STARTED
        node = await self.get_db_node(session_factory, name)
        assert task.build_node_id == node.id
        assert await self.get_task(node_name(), arch) is None

    async def test_build_done_from_another_node(self, arch, seed_tasks):
        (task_id,) = await seed_tasks(1)
        owner, other = node_name(), node_name()
        assert await self.get_task(owner, arch) == task_id
        await self.ping(other, arch)
        response = await self.build_done(task_id, other)
        assert response.status_code == self.status_codes.HTTP_409_CONFLICT
        response = await self.build_done(task_id, node_name())
        assert response.status_code == self.status_codes.HTTP_409_CONFLICT
        response = await self.build_done(task_id, owner)
        assert response.status_code == self.status_codes.HTTP_200_OK

    async def test_build_done_without_node_name(
        self,
        arch,
        seed_tasks,
        session_factory,
    ):
        (task_id,) = await seed_tasks(1)
        name = node_name()
        assert await self.get_task(name, arch) == task_id
        response = await self.build_done(task_id, None)
        assert response.status_code == self.status_codes.HTTP_200_OK
        task = await self.get_db_task(session_factory, task_id)
        assert task.node_reported_at is not None

    async def prepare_held_task(
        self,
        arch: str,
        seed_tasks,
        session_factory,
        name: str,
        instance_id: str,
    ) -> int:
        """A task held by the node and missing from its pings for long."""
        (task_id,) = await seed_tasks(1)
        assert await self.get_task(name, arch) == task_id
        await self.ping(
            name,
            arch,
            active_tasks=[task_id],
            instance_id=instance_id,
        )
        claimed_at = datetime.datetime.utcnow() - datetime.timedelta(
            seconds=settings.build_node_reconcile_grace + 30,
        )
        await self.update_tasks(
            session_factory,
            [task_id],
            claimed_at=claimed_at,
        )
        return task_id

    @staticmethod
    def seconds_ago(seconds: int) -> datetime.datetime:
        return datetime.datetime.utcnow() - datetime.timedelta(
            seconds=seconds,
        )

    async def test_another_instance_of_online_node(
        self,
        arch,
        seed_tasks,
        session_factory,
        caplog,
    ):
        name = node_name()
        task_id = await self.prepare_held_task(
            arch,
            seed_tasks,
            session_factory,
            name,
            "builder-a.100",
        )
        node = await self.get_db_node(session_factory, name)
        assert node.instance_id == "builder-a.100"
        assert node.instance_changed_at is None

        await self.ping(name, arch, instance_id="builder-b.200")
        task = await self.get_db_task(session_factory, task_id)
        assert task.status == BuildTaskStatus.STARTED, (
            "Another instance returned the task to the queue"
        )
        assert task.build_node_id == node.id
        node = await self.get_db_node(session_factory, name)
        assert node.instance_id == "builder-b.200"
        assert node.instance_changed_at is not None
        assert any(
            record.levelname == "WARNING"
            and name in record.getMessage()
            and "builder-a.100" in record.getMessage()
            and "builder-b.200" in record.getMessage()
            for record in caplog.records
        ), "No warning about two instances of the node"

        # The same instance again, the first one may still be running
        changed_at = node.instance_changed_at
        await self.ping(name, arch, instance_id="builder-b.200")
        await self.ping(name, arch, instance_id="builder-b.200")
        task = await self.get_db_task(session_factory, task_id)
        assert task.status == BuildTaskStatus.STARTED, (
            "Pings in a row of another instance returned the task"
        )
        assert task.build_node_id == node.id
        node = await self.get_db_node(session_factory, name)
        assert node.instance_changed_at == changed_at

    async def test_reconcile_resumes_after_instance_change(
        self,
        arch,
        seed_tasks,
        session_factory,
    ):
        name = node_name()
        task_id = await self.prepare_held_task(
            arch,
            seed_tasks,
            session_factory,
            name,
            "builder-a.100",
        )
        await self.ping(name, arch, instance_id="builder-b.200")
        # The first instance didn't ping for the offline timeout, it's gone
        await self.update_node(
            session_factory,
            name,
            instance_changed_at=self.seconds_ago(
                settings.build_node_offline_timeout + 1,
            ),
        )

        await self.ping(name, arch, instance_id="builder-b.200")
        task = await self.get_db_task(session_factory, task_id)
        assert task.status == BuildTaskStatus.IDLE
        assert task.build_node_id is None
        node = await self.get_db_node(session_factory, name)
        assert node.instance_id == "builder-b.200"

    async def test_two_instances_in_parallel(
        self,
        arch,
        seed_tasks,
        session_factory,
    ):
        """Two instances keep the reconciliation off while both run.

        No task of one instance is returned by the other one. The tasks
        lost by the instances wait until only one of them stays.
        """
        name = node_name()
        task_a = await self.prepare_held_task(
            arch,
            seed_tasks,
            session_factory,
            name,
            "builder-a.100",
        )
        (task_b,) = await seed_tasks(1)
        assert await self.get_task(name, arch) == task_b
        await self.ping(
            name,
            arch,
            active_tasks=[task_b],
            instance_id="builder-b.200",
        )
        await self.update_tasks(
            session_factory,
            [task_b],
            claimed_at=self.seconds_ago(
                settings.build_node_reconcile_grace + 30,
            ),
        )

        # Much longer than the offline timeout in total
        pings = [("builder-a.100", task_a), ("builder-b.200", task_b)] * 3
        for instance_id, task_id in pings:
            aged = self.seconds_ago(settings.build_node_offline_timeout - 5)
            await self.update_node(
                session_factory,
                name,
                instance_changed_at=aged,
            )
            await self.ping(
                name,
                arch,
                active_tasks=[task_id],
                instance_id=instance_id,
            )
            for held_task in (task_a, task_b):
                task = await self.get_db_task(session_factory, held_task)
                assert task.status == BuildTaskStatus.STARTED, (
                    f"Ping of {instance_id} returned task {held_task}"
                )
            node = await self.get_db_node(session_factory, name)
            assert node.instance_changed_at > aged

        # The second instance stopped, the first one runs alone
        await self.ping(
            name,
            arch,
            active_tasks=[task_a],
            instance_id="builder-a.100",
        )
        task = await self.get_db_task(session_factory, task_b)
        assert task.status == BuildTaskStatus.STARTED
        await self.update_node(
            session_factory,
            name,
            instance_changed_at=self.seconds_ago(
                settings.build_node_offline_timeout + 1,
            ),
        )
        await self.ping(
            name,
            arch,
            active_tasks=[task_a],
            instance_id="builder-a.100",
        )
        task = await self.get_db_task(session_factory, task_a)
        assert task.status == BuildTaskStatus.STARTED
        task = await self.get_db_task(session_factory, task_b)
        assert task.status == BuildTaskStatus.IDLE
        assert task.build_node_id is None

    async def test_another_instance_of_offline_node(
        self,
        arch,
        seed_tasks,
        session_factory,
    ):
        name = node_name()
        task_id = await self.prepare_held_task(
            arch,
            seed_tasks,
            session_factory,
            name,
            "builder-a.100",
        )
        # Even if the node changed its instance recently before that
        await self.update_node(
            session_factory,
            name,
            last_seen=self.seconds_ago(
                settings.build_node_offline_timeout + 10,
            ),
            instance_changed_at=self.seconds_ago(10),
        )

        # The node was restarted, the task is lost
        await self.ping(name, arch, instance_id="builder-a.300")
        task = await self.get_db_task(session_factory, task_id)
        assert task.status == BuildTaskStatus.IDLE
        assert task.build_node_id is None
        node = await self.get_db_node(session_factory, name)
        assert node.instance_id == "builder-a.300"
        assert node.instance_changed_at is None

    async def test_confirmed_restart_returns_old_tasks_at_once(
        self,
        arch,
        seed_tasks,
        session_factory,
        caplog,
    ):
        caplog.set_level("INFO")
        name = node_name()
        lost, carried, fresh = await seed_tasks(3)
        for task_id in (lost, carried):
            assert (
                await self.get_task(name, arch, instance_id="builder-a.100")
                == task_id
            )
        await self.ping(
            name,
            arch,
            active_tasks=[lost, carried],
            instance_id="builder-a.100",
        )
        # The node is restarted at once, the new process asks for a task
        # before its first ping and doesn't report it in the ping yet
        assert (
            await self.get_task(name, arch, instance_id="builder-a.200")
            == fresh
        )
        await self.ping(
            name,
            arch,
            active_tasks=[carried],
            instance_id="builder-a.200",
            previous_instance_id="builder-a.100",
        )

        task = await self.get_db_task(session_factory, lost)
        assert task.status == BuildTaskStatus.IDLE, (
            "The task of the previous process waits for the grace"
        )
        assert task.build_node_id is None
        assert task.claimed_by_instance is None
        node = await self.get_db_node(session_factory, name)
        task = await self.get_db_task(session_factory, carried)
        assert task.status == BuildTaskStatus.STARTED
        assert task.build_node_id == node.id
        task = await self.get_db_task(session_factory, fresh)
        assert task.status == BuildTaskStatus.STARTED, (
            "The task of the new process is returned within the grace"
        )
        assert task.claimed_by_instance == "builder-a.200"
        assert node.instance_id == "builder-a.200"
        assert node.instance_changed_at is None
        assert any(
            record.levelname == "INFO"
            and name in record.getMessage()
            and "restarted" in record.getMessage()
            for record in caplog.records
        ), "No message about the restart"
        assert not any(
            "Two instances" in record.getMessage()
            for record in caplog.records
        )

        # The new process keeps sending its previous instance, it's no
        # restart anymore, and its task is reconciled after the grace
        await self.update_tasks(
            session_factory,
            [fresh],
            claimed_at=self.seconds_ago(
                settings.build_node_reconcile_grace + 30,
            ),
        )
        await self.ping(
            name,
            arch,
            active_tasks=[carried],
            instance_id="builder-a.200",
            previous_instance_id="builder-a.100",
        )
        task = await self.get_db_task(session_factory, fresh)
        assert task.status == BuildTaskStatus.IDLE
        task = await self.get_db_task(session_factory, carried)
        assert task.status == BuildTaskStatus.STARTED

    @pytest.mark.parametrize("previous_instance_id", [None, "builder-a.99"])
    async def test_unconfirmed_restart_keeps_the_tasks(
        self,
        arch,
        seed_tasks,
        session_factory,
        caplog,
        previous_instance_id,
    ):
        name = node_name()
        (task_id,) = await seed_tasks(1)
        assert (
            await self.get_task(name, arch, instance_id="builder-a.100")
            == task_id
        )
        await self.ping(
            name,
            arch,
            active_tasks=[task_id],
            instance_id="builder-a.100",
        )
        await self.update_tasks(
            session_factory,
            [task_id],
            claimed_at=self.seconds_ago(
                settings.build_node_reconcile_grace + 30,
            ),
        )

        await self.ping(
            name,
            arch,
            instance_id="builder-a.200",
            previous_instance_id=previous_instance_id,
        )
        task = await self.get_db_task(session_factory, task_id)
        assert task.status == BuildTaskStatus.STARTED
        node = await self.get_db_node(session_factory, name)
        assert node.instance_id == "builder-a.200"
        assert node.instance_changed_at is not None
        assert any(
            record.levelname == "WARNING" and name in record.getMessage()
            for record in caplog.records
        ), "No warning about two instances of the node"

    async def test_confirmed_restart_while_another_instance_runs(
        self,
        arch,
        seed_tasks,
        session_factory,
    ):
        """Two hosts with the same name, one of them is restarted.

        The other host doesn't have the file with the previous instance,
        but the restarted one does, and its confirmed restart mustn't return
        the tasks of the other host.
        """
        name = node_name()
        task_a, task_b = await seed_tasks(2)
        assert (
            await self.get_task(name, arch, instance_id="builder-a.100")
            == task_a
        )
        await self.ping(
            name,
            arch,
            active_tasks=[task_a],
            instance_id="builder-a.100",
            previous_instance_id="builder-a.50",
        )
        assert (
            await self.get_task(name, arch, instance_id="builder-b.200")
            == task_b
        )
        # The previous process of the other host
        await self.ping(
            name,
            arch,
            active_tasks=[task_b],
            instance_id="builder-b.200",
            previous_instance_id="builder-b.150",
        )
        await self.update_tasks(
            session_factory,
            [task_a, task_b],
            claimed_at=self.seconds_ago(
                settings.build_node_reconcile_grace + 30,
            ),
        )
        await self.ping(
            name,
            arch,
            active_tasks=[task_a],
            instance_id="builder-a.100",
            previous_instance_id="builder-a.50",
        )
        for task_id in (task_a, task_b):
            task = await self.get_db_task(session_factory, task_id)
            assert task.status == BuildTaskStatus.STARTED

        # The first host is restarted right after its ping
        await self.ping(
            name,
            arch,
            instance_id="builder-a.300",
            previous_instance_id="builder-a.100",
        )
        task = await self.get_db_task(session_factory, task_b)
        assert task.status == BuildTaskStatus.STARTED, (
            "The restart returned the task of the other host"
        )
        node = await self.get_db_node(session_factory, name)
        assert node.instance_id == "builder-a.300"
        assert node.instance_changed_at is not None

    @pytest.mark.parametrize("with_node_name", [True, False])
    async def test_repeated_build_done_is_processed_once(
        self,
        arch,
        seed_tasks,
        session_factory,
        monkeypatch,
        with_node_name,
    ):
        sent = []
        monkeypatch.setattr(
            "dramatiq.Actor.send",
            lambda actor, *args, **kwargs: sent.append(args),
        )
        (task_id,) = await seed_tasks(1)
        name = node_name()
        assert await self.get_task(name, arch) == task_id
        reporter = name if with_node_name else None
        response = await self.build_done(task_id, reporter)
        assert response.status_code == self.status_codes.HTTP_200_OK
        reported_at = (
            await self.get_db_task(session_factory, task_id)
        ).node_reported_at
        # The node retries the request after a read timeout
        response = await self.build_done(task_id, reporter)
        assert response.status_code == self.status_codes.HTTP_200_OK
        assert response.json() == {"ok": True}
        assert len(sent) == 1, "The results are sent to dramatiq twice"
        task = await self.get_db_task(session_factory, task_id)
        assert task.node_reported_at == reported_at

    async def test_build_done_for_returned_task(
        self,
        arch,
        seed_tasks,
        session_factory,
    ):
        (task_id,) = await seed_tasks(1)
        name = node_name()
        assert await self.get_task(name, arch) == task_id
        claimed_at = datetime.datetime.utcnow() - datetime.timedelta(
            seconds=settings.build_node_reconcile_grace + 30,
        )
        await self.update_tasks(
            session_factory,
            [task_id],
            claimed_at=claimed_at,
        )
        # The node lost the task, it's returned to the queue
        await self.ping(name, arch)
        task = await self.get_db_task(session_factory, task_id)
        assert task.status == BuildTaskStatus.IDLE

        response = await self.build_done(task_id, name)
        assert response.status_code == self.status_codes.HTTP_409_CONFLICT
        task = await self.get_db_task(session_factory, task_id)
        assert task.status == BuildTaskStatus.IDLE
        assert task.build_node_id is None, "The node adopted the idle task"
        assert task.node_reported_at is None
        # It's still in the queue
        assert await self.get_task(node_name(), arch) == task_id

    async def test_build_done_for_legacy_task(
        self,
        arch,
        seed_tasks,
        session_factory,
    ):
        """A task claimed by a node without node_name isn't bound to a node."""
        (task_id,) = await seed_tasks(1)
        assert await self.get_task(None, arch) == task_id
        name = node_name()
        await self.ping(name, arch)
        response = await self.build_done(task_id, name)
        assert response.status_code == self.status_codes.HTTP_200_OK
        task = await self.get_db_task(session_factory, task_id)
        node = await self.get_db_node(session_factory, name)
        assert task.build_node_id == node.id
        assert task.node_reported_at is not None


class TestDispatchLimit(BuildNodesTestCase):
    """A task the nodes never send a result for isn't handed out forever."""

    @staticmethod
    def capture_sent(monkeypatch) -> typing.List[typing.Tuple[str, dict]]:
        sent = []
        monkeypatch.setattr(
            "dramatiq.Actor.send",
            lambda actor, message, *args, **kwargs: sent.append(
                (actor.actor_name, message)
            ),
        )
        return sent

    @staticmethod
    def seconds_ago(seconds: int) -> datetime.datetime:
        return datetime.datetime.utcnow() - datetime.timedelta(
            seconds=seconds,
        )

    async def lose_task(self, session_factory, name, arch, task_id):
        """The node doesn't report the task in its ping anymore."""
        await self.update_tasks(
            session_factory,
            [task_id],
            claimed_at=self.seconds_ago(
                settings.build_node_reconcile_grace + 30,
            ),
        )
        await self.ping(name, arch)
        task = await self.get_db_task(session_factory, task_id)
        assert task.status == BuildTaskStatus.IDLE

    async def test_task_is_failed_after_max_dispatches(
        self,
        arch,
        seed_tasks,
        session_factory,
        monkeypatch,
        caplog,
    ):
        monkeypatch.setattr(settings, "build_node_task_max_dispatches", 3)
        sent = self.capture_sent(monkeypatch)
        stuck, other = await seed_tasks(2)
        first, second, third, fourth = [node_name() for _ in range(4)]

        # Every way back to the queue keeps the count: the ping of the node
        assert await self.get_task(first, arch) == stuck
        await self.lose_task(session_factory, first, arch, stuck)
        # the reclaim from a dead node
        assert await self.get_task(second, arch) == stuck
        await self.update_node(
            session_factory,
            second,
            last_seen=self.seconds_ago(
                settings.build_node_task_reclaim_timeout + 10,
            ),
        )
        assert await self.get_task(third, arch) == stuck
        task = await self.get_db_task(session_factory, stuck)
        assert task.dispatch_count == 3
        assert task.dispatch_nodes == [first, second, third]
        await self.lose_task(session_factory, third, arch, stuck)

        # The next attempt fails the task and hands out the next one
        assert await self.get_task(fourth, arch) == other
        task = await self.get_db_task(session_factory, stuck)
        assert task.dispatch_count == 3
        assert task.status == BuildTaskStatus.STARTED
        assert task.node_reported_at is not None
        assert task.build_node_id is None
        # The error is public, the names of the nodes are for the log only
        assert task.error == (
            "The task was handed out to build nodes 3 times without a result"
        )
        assert sent == [(
            "build_done",
            {
                "task_id": stuck,
                "status": "failed",
                "artifacts": [],
                "stats": {},
                "is_cas_authenticated": False,
                "alma_commit_cas_hash": None,
                "git_commit_hash": None,
                "node_name": None,
            },
        )]
        assert any(
            record.levelname == "WARNING"
            and str(stuck) in record.getMessage()
            and "3 times" in record.getMessage()
            and all(
                name in record.getMessage()
                for name in (first, second, third)
            )
            for record in caplog.records
        ), "No warning about the failed task"
        # It's not handed out while dramatiq processes the result
        await self.lose_task(session_factory, fourth, arch, other)
        assert await self.get_task(node_name(), arch) == other
        assert await self.get_task(node_name(), arch) is None
        assert len(sent) == 1

    async def test_legacy_task_is_failed_after_max_dispatches(
        self,
        arch,
        seed_tasks,
        session_factory,
        monkeypatch,
    ):
        monkeypatch.setattr(settings, "build_node_task_max_dispatches", 2)
        sent = self.capture_sent(monkeypatch)
        stuck, other = await seed_tasks(2)
        for attempt in (1, 2):
            assert await self.get_task(None, arch) == stuck
            task = await self.get_db_task(session_factory, stuck)
            assert task.dispatch_count == attempt
            # No ping refreshed its ts for long
            await self.update_tasks(
                session_factory,
                [stuck],
                ts=self.seconds_ago(21 * 60),
            )

        assert await self.get_task(None, arch) == other
        task = await self.get_db_task(session_factory, stuck)
        assert task.dispatch_count == 2
        assert task.dispatch_nodes == [None, None]
        assert task.node_reported_at is not None
        assert task.error == (
            "The task was handed out to build nodes 2 times without a result"
        )
        assert [(actor, message["task_id"], message["status"])
                for actor, message in sent] == [("build_done", stuck, "failed")]
        assert await self.get_task(None, arch) is None

    async def test_finished_task_is_not_affected(
        self,
        arch,
        seed_tasks,
        session_factory,
        monkeypatch,
    ):
        monkeypatch.setattr(settings, "build_node_task_max_dispatches", 1)
        sent = self.capture_sent(monkeypatch)
        (task_id,) = await seed_tasks(1)
        name = node_name()
        assert await self.get_task(name, arch) == task_id
        response = await self.build_done(task_id, name)
        assert response.status_code == self.status_codes.HTTP_200_OK
        task = await self.get_db_task(session_factory, task_id)
        assert task.dispatch_count == 1
        assert task.error is None
        assert [(message["task_id"], message["status"])
                for _, message in sent] == [(task_id, "done")]

    @pytest.mark.parametrize(
        "endpoint",
        ["restart-failed", "parallel-restart-failed"],
    )
    async def test_restart_by_user_resets_the_count(
        self,
        arch,
        seed_tasks,
        session_factory,
        monkeypatch,
        endpoint,
    ):
        monkeypatch.setattr(settings, "build_node_task_max_dispatches", 2)
        self.capture_sent(monkeypatch)
        task_ids = await seed_tasks(2)
        await self.update_tasks(
            session_factory,
            task_ids,
            status=BuildTaskStatus.FAILED,
            dispatch_count=2,
            dispatch_nodes=["a", "b"],
        )
        build_id = (await self.get_db_task(session_factory, task_ids[0])).build_id
        response = await self.make_request(
            "patch",
            f"/api/v1/builds/{build_id}/{endpoint}",
        )
        message = f"Cannot restart the build:\n{response.text}"
        assert response.status_code == self.status_codes.HTTP_200_OK, message
        for task_id in task_ids:
            task = await self.get_db_task(session_factory, task_id)
            assert task.status == BuildTaskStatus.IDLE
            assert task.dispatch_count == 0
            assert task.dispatch_nodes is None
        # It gets all the attempts again
        assert await self.get_task(node_name(), arch) == task_ids[0]

    async def test_failed_task_is_processed_like_failed_build_done(
        self,
        regular_build,
        start_build,
        get_rpm_packages_info,
        session_factory,
        monkeypatch,
    ):
        """The result made up by the server goes through build_done.

        The dependent tasks, the build and its test tasks are processed
        as for a failed build_done of a node, without any artifacts.
        """
        sent = self.capture_sent(monkeypatch)
        async with session_factory() as session:
            tasks = (
                await session.execute(
                    select(models.BuildTask)
                    .where(models.BuildTask.build_id == regular_build.id)
                    .order_by(models.BuildTask.id)
                )
            ).scalars().all()
            stuck = tasks[0]
            stuck.dispatch_count = settings.build_node_task_max_dispatches
            stuck.dispatch_nodes = ["builder-a"]
            await build_node_crud._fail_undeliverable_task(
                session,
                stuck,
                datetime.datetime.utcnow(),
            )
            await session.commit()
        # The first task of the project builds the sources
        assert stuck.arch == "src"
        ((actor, message),) = sent
        assert actor == "sources_build_done"

        await _build_done(BuildDone(**message))

        async with session_factory() as session:
            tasks = {
                task.id: task
                for task in (
                    await session.execute(
                        select(models.BuildTask).where(
                            models.BuildTask.build_id == regular_build.id
                        )
                    )
                ).scalars()
            }
            build = await session.get(models.Build, regular_build.id)
        failed = tasks.pop(stuck.id)
        assert failed.status == BuildTaskStatus.FAILED
        assert "without a result" in failed.error
        assert failed.finished_at is not None
        # The other arches of the project are fast failed as usual
        assert tasks
        for task in tasks.values():
            assert task.status == BuildTaskStatus.FAILED
            assert task.error.startswith("Fast failed")
        assert build.finished_at is not None


class TestBuildNodesRegistry(BuildNodesTestCase):
    @staticmethod
    async def last_node_id(session_factory) -> int:
        async with session_factory() as session:
            return (
                await session.execute(
                    text("SELECT last_value FROM build_nodes_id_seq")
                )
            ).scalar_one()

    async def test_known_node_spends_no_ids(
        self,
        arch,
        seed_tasks,
        session_factory,
    ):
        await seed_tasks(1)
        first = node_name()
        await self.ping(first, arch, instance_id="builder.1")
        first_id = (await self.get_db_node(session_factory, first)).id
        assert await self.last_node_id(session_factory) == first_id

        for _ in range(5):
            await self.ping(first, arch, instance_id="builder.1")
        assert await self.get_task(first, arch) is not None
        assert await self.get_task(first, arch) is None
        assert await self.last_node_id(session_factory) == first_id

        second = node_name()
        await self.ping(second, arch)
        second_id = (await self.get_db_node(session_factory, second)).id
        assert second_id == first_id + 1
        assert await self.last_node_id(session_factory) == second_id

    async def test_update_keeps_created_at(self, arch, session_factory):
        name = node_name()
        await self.ping(name, arch, capacity=2)
        created = await self.get_db_node(session_factory, name)
        await self.ping(name, arch, capacity=4, instance_id="builder.7")
        node = await self.get_db_node(session_factory, name)
        assert node.id == created.id
        assert node.created_at == created.created_at
        assert node.last_seen > created.last_seen
        assert node.capacity == 4
        assert node.instance_id == "builder.7"
        assert node.resources == RESOURCES

    async def test_concurrent_first_registration(self, session_factory):
        name = node_name()
        now = datetime.datetime.utcnow()
        async with session_factory() as first, session_factory() as second:
            first_node = await build_nodes_crud.register_build_node(
                first,
                name,
                now,
            )
            # Doesn't see the uncommitted row, so it inserts too
            # and waits for the first transaction on the conflict
            second_registration = asyncio.create_task(
                build_nodes_crud.register_build_node(second, name, now)
            )
            await asyncio.sleep(0.3)
            assert not second_registration.done()
            await first.commit()
            second_node = await second_registration
            await second.commit()
        assert second_node.id == first_node.id
        async with session_factory() as session:
            count = (
                await session.execute(
                    select(models.BuildNode.id).where(
                        models.BuildNode.name == name
                    )
                )
            ).all()
        assert len(count) == 1


class TestBuildNodesEndpoints(BuildNodesTestCase):
    async def find_node(self, name: str) -> dict:
        response = await self.make_request("get", "/api/v1/build_nodes/")
        message = f"Cannot list build nodes:\n{response.text}"
        assert response.status_code == self.status_codes.HTTP_200_OK, message
        nodes = {node["name"]: node for node in response.json()}
        assert name in nodes, f"{name} is not in {list(nodes)}"
        return nodes[name]

    async def test_list_nodes(self, arch, seed_tasks, session_factory):
        task_ids = await seed_tasks(2)
        name = node_name()
        await self.ping(name, arch, capacity=4, instance_id="builder.42")
        assert await self.get_task(name, arch, capacity=4) == task_ids[0]
        await self.update_tasks(
            session_factory,
            [task_ids[0]],
            status=BuildTaskStatus.COMPLETED,
            finished_at=datetime.datetime.utcnow(),
        )
        assert await self.get_task(name, arch, capacity=4) == task_ids[1]

        node = await self.find_node(name)
        assert node["online"] is True
        assert node["enabled"] is True
        assert node["drain"] is False
        assert node["maintenance"] is False
        assert node["version"] == "1.0.0"
        assert node["instance_id"] == "builder.42"
        assert node["supported_arches"] == [arch]
        assert node["node_type"] == "x86_64"
        assert node["pesign_support"] is False
        assert node["capacity"] == 4
        assert node["capacity_override"] is None
        assert node["effective_capacity"] == 4
        assert node["last_seen"]
        assert node["resources"] == RESOURCES
        assert node["resources_updated_at"]
        assert node["active_tasks_count"] == 1
        (active,) = node["active_tasks"]
        assert active["id"] == task_ids[1]
        assert active["arch"] == arch
        assert active["build_id"]
        assert active["ref_url"].startswith("https://git.almalinux.org/")
        assert active["claimed_at"]
        assert active["dispatch_count"] == 1
        assert active["dispatch_nodes"] == [name]
        assert node["stats_24h"] == {"done": 1, "failed": 0, "excluded": 0}

    async def test_offline_node(self, arch, session_factory):
        name = node_name()
        await self.ping(name, arch)
        last_seen = datetime.datetime.utcnow() - datetime.timedelta(
            seconds=settings.build_node_offline_timeout + 10,
        )
        await self.update_node(session_factory, name, last_seen=last_seen)
        node = await self.find_node(name)
        assert node["online"] is False

    async def test_node_details(self, arch, seed_tasks, session_factory):
        task_ids = await seed_tasks(2)
        name = node_name()
        for _ in task_ids:
            await self.get_task(name, arch)
        await self.update_tasks(
            session_factory,
            [task_ids[0]],
            status=BuildTaskStatus.FAILED,
            finished_at=datetime.datetime.utcnow(),
        )
        node = await self.get_db_node(session_factory, name)
        response = await self.make_request(
            "get",
            f"/api/v1/build_nodes/{node.id}",
        )
        message = f"Cannot get build node:\n{response.text}"
        assert response.status_code == self.status_codes.HTTP_200_OK, message
        details = response.json()
        assert details["name"] == name
        assert details["active_tasks_count"] == 1
        assert details["stats_24h"]["failed"] == 1
        recent = {task["id"]: task for task in details["recent_tasks"]}
        assert set(recent) == set(task_ids)
        assert recent[task_ids[0]]["status"] == BuildTaskStatus.FAILED
        assert recent[task_ids[0]]["finished_at"]
        assert recent[task_ids[1]]["status"] == BuildTaskStatus.STARTED
        assert recent[task_ids[1]]["ref_url"]
        assert recent[task_ids[1]]["dispatch_count"] == 1
        assert recent[task_ids[1]]["dispatch_nodes"] == [name]

        response = await self.make_request(
            "get",
            "/api/v1/build_nodes/999999",
        )
        assert response.status_code == self.status_codes.HTTP_404_NOT_FOUND

    async def test_queue(self, arch, seed_tasks):
        await seed_tasks(3)
        name = node_name()
        await self.ping(name, arch, capacity=4)
        assert await self.get_task(name, arch, capacity=4)
        response = await self.make_request(
            "get",
            "/api/v1/build_nodes/queue",
        )
        message = f"Cannot get queue:\n{response.text}"
        assert response.status_code == self.status_codes.HTTP_200_OK, message
        queue = {item["arch"]: item for item in response.json()}
        assert queue[arch] == {
            "arch": arch,
            "queued_tasks": 2,
            "online_nodes": 1,
            "total_capacity": 4,
            "active_tasks": 1,
            "accepting_active_tasks": 1,
            "unregistered_active_tasks": 0,
        }

    async def get_queue(self, arch: str) -> dict:
        response = await self.make_request(
            "get",
            "/api/v1/build_nodes/queue",
        )
        message = f"Cannot get queue:\n{response.text}"
        assert response.status_code == self.status_codes.HTTP_200_OK, message
        queue = {item["arch"]: item for item in response.json()}
        return queue[arch]

    async def test_queue_active_tasks(self, arch, seed_tasks, session_factory):
        task_ids = await seed_tasks(6)
        accepting, draining, offline = node_name(), node_name(), node_name()
        got = {
            accepting: [
                await self.get_task(accepting, arch, capacity=4),
                await self.get_task(accepting, arch, capacity=4),
            ],
            draining: [await self.get_task(draining, arch, capacity=4)],
            offline: [await self.get_task(offline, arch, capacity=4)],
            # Nodes without node_name
            "legacy": [await self.get_task(None, arch)],
            "expired": [await self.get_task(None, arch)],
        }
        assert sorted(sum(got.values(), [])) == task_ids
        # Reported tasks don't occupy a slot on the node
        response = await self.build_done(got[accepting][0], accepting)
        assert response.status_code == self.status_codes.HTTP_200_OK
        await self.update_node(session_factory, draining, drain=True)
        last_seen = datetime.datetime.utcnow() - datetime.timedelta(
            seconds=settings.build_node_offline_timeout + 10,
        )
        await self.update_node(session_factory, offline, last_seen=last_seen)
        expired_ts = datetime.datetime.utcnow() - datetime.timedelta(
            minutes=30,
        )
        await self.update_tasks(session_factory, got["expired"], ts=expired_ts)

        assert await self.get_queue(arch) == {
            "arch": arch,
            # The expired task of the node without node_name
            "queued_tasks": 1,
            "online_nodes": 1,
            "total_capacity": 4,
            # The draining, offline, accepting and legacy nodes
            "active_tasks": 4,
            "accepting_active_tasks": 1,
            "unregistered_active_tasks": 1,
        }

    async def test_update_node(self, arch, session_factory):
        name = node_name()
        await self.ping(name, arch, capacity=8)
        node = await self.get_db_node(session_factory, name)
        endpoint = f"/api/v1/build_nodes/{node.id}"

        response = await self.make_request(
            "patch",
            endpoint,
            json={"drain": True, "capacity_override": 2},
        )
        message = f"Cannot update build node:\n{response.text}"
        assert response.status_code == self.status_codes.HTTP_200_OK, message
        updated = response.json()
        assert updated["drain"] is True
        assert updated["enabled"] is True
        assert updated["capacity_override"] == 2
        assert updated["effective_capacity"] == 2

        # Omitted fields are kept, null resets the capacity limit
        response = await self.make_request(
            "patch",
            endpoint,
            json={"enabled": False},
        )
        assert response.status_code == self.status_codes.HTTP_200_OK
        assert response.json()["capacity_override"] == 2
        response = await self.make_request(
            "patch",
            endpoint,
            json={"capacity_override": None, "drain": False},
        )
        assert response.status_code == self.status_codes.HTTP_200_OK
        updated = response.json()
        assert updated["enabled"] is False
        assert updated["drain"] is False
        assert updated["capacity_override"] is None
        assert updated["effective_capacity"] == 8

        node = await self.get_db_node(session_factory, name)
        assert node.enabled is False
        assert node.capacity_override is None

        response = await self.make_request(
            "patch",
            endpoint,
            json={"capacity_override": -1},
        )
        assert (
            response.status_code
            == self.status_codes.HTTP_422_UNPROCESSABLE_ENTITY
        )
        response = await self.make_request(
            "patch",
            "/api/v1/build_nodes/999999",
            json={"drain": True},
        )
        assert response.status_code == self.status_codes.HTTP_404_NOT_FOUND

    async def registry_requests(self, session_factory, arch):
        name = node_name()
        await self.ping(name, arch)
        node = await self.get_db_node(session_factory, name)
        return node, [
            ("get", "/api/v1/build_nodes/", None),
            ("get", "/api/v1/build_nodes/queue", None),
            ("get", f"/api/v1/build_nodes/{node.id}", None),
            ("patch", f"/api/v1/build_nodes/{node.id}", {"drain": True}),
        ]

    async def test_regular_user_is_forbidden(self, arch, session_factory):
        node, requests = await self.registry_requests(session_factory, arch)
        token = BaseAsyncTestCase.generate_jwt_token(str(CUSTOM_USER_ID))
        for method, endpoint, payload in requests:
            response = await self.request_as(token, method, endpoint, payload)
            assert (
                response.status_code == self.status_codes.HTTP_403_FORBIDDEN
            ), f"{method} {endpoint}: {response.text}"
        node = await self.get_db_node(session_factory, node.name)
        assert node.drain is False

    async def test_superuser_is_allowed(self, arch, session_factory):
        node, requests = await self.registry_requests(session_factory, arch)
        for method, endpoint, payload in requests:
            response = await self.make_request(
                method,
                endpoint,
                **({"json": payload} if payload is not None else {}),
            )
            assert (
                response.status_code == self.status_codes.HTTP_200_OK
            ), f"{method} {endpoint}: {response.text}"
        node = await self.get_db_node(session_factory, node.name)
        assert node.drain is True

    @pytest.mark.parametrize("token", [None, "not-a-jwt"])
    async def test_unauthenticated_access_is_denied(
        self,
        arch,
        session_factory,
        token,
    ):
        """Every endpoint answers like the superuser-only PATCH did."""
        node, requests = await self.registry_requests(session_factory, arch)
        statuses = set()
        for method, endpoint, payload in requests:
            response = await self.request_as(token, method, endpoint, payload)
            statuses.add(response.status_code)
        assert len(statuses) == 1, statuses
        assert statuses <= {
            self.status_codes.HTTP_401_UNAUTHORIZED,
            self.status_codes.HTTP_403_FORBIDDEN,
        }
        node = await self.get_db_node(session_factory, node.name)
        assert node.drain is False

@pytest.fixture
def build_node_user(session_factory):
    """Create a build node service user, return its token and id."""

    async def _create(
        node_name: typing.Optional[str] = None,
        is_build_node: bool = True,
        is_superuser: bool = False,
    ) -> typing.Tuple[str, int]:
        async with session_factory() as session:
            # The users of the fixtures are inserted with explicit ids,
            # so the sequence of the table can't be relied on
            last_id = (
                await session.execute(select(func.max(models.User.id)))
            ).scalar()
            user = models.User(
                id=(last_id or 0) + 1,
                username=f"build-node-{uuid.uuid4().hex[:8]}",
                email=f"{uuid.uuid4().hex[:8]}@build-nodes.invalid",
                is_active=True,
                is_verified=True,
                is_superuser=is_superuser,
                is_build_node=is_build_node,
                build_node_name=node_name,
            )
            session.add(user)
            await session.commit()
            user_id = user.id
        return BaseAsyncTestCase.generate_jwt_token(str(user_id)), user_id

    return _create


class TestBuildNodeTokens(BuildNodesTestCase):
    async def ping_as(self, token, arch, name: typing.Optional[str]):
        payload = {"active_tasks": []}
        if name is not None:
            payload["node_name"] = name
            payload["node_info"] = self.node_info(arch)
        return await self.request_as(
            token, "post", "/api/v1/build_node/ping", payload,
        )

    async def get_task_as(self, token, arch, name: typing.Optional[str]):
        payload = {"supported_arches": [arch], "excluded_packages": []}
        if name is not None:
            payload["node_name"] = name
            payload["node_info"] = self.node_info(arch)
        return await self.request_as(
            token, "post", "/api/v1/build_node/get_task", payload,
        )

    async def build_done_as(self, token, task_id, name: typing.Optional[str]):
        payload = {
            "task_id": task_id,
            "status": "done",
            "artifacts": [],
            "stats": {},
        }
        if name is not None:
            payload["node_name"] = name
        return await self.request_as(
            token, "post", "/api/v1/build_node/build_done", payload,
        )

    async def test_shared_token_serves_any_node(
        self,
        arch,
        seed_tasks,
        build_node_user,
        monkeypatch,
    ):
        sent = TestDispatchLimit.capture_sent(monkeypatch)
        first_task, second_task = await seed_tasks(2)
        token, _ = await build_node_user()
        first, second = node_name(), node_name()
        for name in (first, second, None):
            response = await self.ping_as(token, arch, name)
            assert response.status_code == 200, response.text
        response = await self.get_task_as(token, arch, first)
        assert response.status_code == 200, response.text
        assert response.json()["id"] == first_task
        response = await self.get_task_as(token, arch, second)
        assert response.json()["id"] == second_task
        response = await self.build_done_as(token, second_task, second)
        assert response.status_code == 200, response.text
        assert response.json() == {"ok": True}
        assert len(sent) == 1

    async def test_bound_token_serves_its_node_only(
        self,
        arch,
        seed_tasks,
        session_factory,
        build_node_user,
        monkeypatch,
    ):
        sent = TestDispatchLimit.capture_sent(monkeypatch)
        (task_id,) = await seed_tasks(1)
        own, other = node_name(), node_name()
        token, _ = await build_node_user(node_name=own)
        for name in (other, None):
            response = await self.ping_as(token, arch, name)
            assert response.status_code == 403, name
            response = await self.get_task_as(token, arch, name)
            assert response.status_code == 403, name
        task = await self.get_db_task(session_factory, task_id)
        assert task.status == BuildTaskStatus.IDLE
        async with session_factory() as session:
            registered = (
                await session.execute(
                    select(models.BuildNode.id).where(
                        models.BuildNode.name == other
                    )
                )
            ).all()
        assert registered == []

        response = await self.ping_as(token, arch, own)
        assert response.status_code == 200, response.text
        response = await self.get_task_as(token, arch, own)
        assert response.json()["id"] == task_id
        for name in (other, None):
            response = await self.build_done_as(token, task_id, name)
            assert response.status_code == 403, name
        assert sent == []
        response = await self.build_done_as(token, task_id, own)
        assert response.status_code == 200, response.text
        assert len(sent) == 1

    async def test_regular_user_is_forbidden(self, arch, seed_tasks):
        (task_id,) = await seed_tasks(1)
        token = BaseAsyncTestCase.generate_jwt_token(str(CUSTOM_USER_ID))
        name = node_name()
        for response in (
            await self.ping_as(token, arch, name),
            await self.ping_as(token, arch, None),
            await self.get_task_as(token, arch, name),
            await self.get_task_as(token, arch, None),
            await self.build_done_as(token, task_id, name),
        ):
            assert response.status_code == 403, response.request.url

    async def test_superuser_is_accepted_with_warning(
        self,
        arch,
        monkeypatch,
        caplog,
    ):
        monkeypatch.setattr(auth, "_superuser_node_warnings", {})
        name = node_name()
        for _ in range(3):
            response = await self.ping_as(self.token, arch, name)
            assert response.status_code == 200, response.text
        warnings = [
            record
            for record in caplog.records
            if record.levelname == "WARNING"
            and "token of superuser" in record.getMessage()
        ]
        assert len(warnings) == 1

    @pytest.mark.parametrize(
        "node_name_, is_superuser",
        [(None, False), ("bound-node", False), (None, True)],
    )
    async def test_node_token_gives_no_other_access(
        self,
        build_node_user,
        node_name_,
        is_superuser,
    ):
        token, _ = await build_node_user(
            node_name=node_name_,
            is_superuser=is_superuser,
        )
        for method, endpoint, payload in (
            ("post", "/api/v1/builds/", {}),
            ("get", "/api/v1/build_nodes/", None),
            ("get", "/api/v1/build_nodes/queue", None),
            ("post", "/api/v1/platforms/", {}),
            # Superuser-only
            (
                "put",
                f"/api/v1/users/{CUSTOM_USER_ID}",
                {"id": CUSTOM_USER_ID},
            ),
        ):
            response = await self.request_as(token, method, endpoint, payload)
            assert response.status_code == 403, (endpoint, response.text)

    @pytest.fixture(autouse=True)
    async def users_sequence(self, session_factory):
        """The script creates users by the sequence of the table, which
        the users of the fixtures inserted with explicit ids didn't move."""
        async with session_factory() as session:
            await session.execute(
                text(
                    "SELECT setval('users_id_seq', "
                    "(SELECT max(id) FROM users))"
                )
            )
            await session.commit()

    @staticmethod
    async def run_token_script(*argv: str) -> typing.Optional[str]:
        args = build_node_token.parse_args(list(argv))
        return await build_node_token.issue_or_revoke(args)

    @staticmethod
    def token_claims(token: str) -> dict:
        return jwt.decode(token, options={"verify_signature": False})

    async def test_script_issues_shared_token_without_expiry(self, arch):
        username = f"build-nodes-{uuid.uuid4().hex[:8]}"
        token = await self.run_token_script("-u", username)
        assert "exp" not in self.token_claims(token)
        for name in (node_name(), node_name(), None):
            response = await self.ping_as(token, arch, name)
            assert response.status_code == 200, response.text
        response = await self.request_as(
            token, "get", "/api/v1/build_nodes/", None,
        )
        assert response.status_code == 403
        # Revoking the user rejects the token that never expires
        assert await self.run_token_script("-u", username, "--revoke") is None
        response = await self.ping_as(token, arch, None)
        assert response.status_code == 401, response.text
        with pytest.raises(SystemExit, match="revoked"):
            await self.run_token_script("-u", username)

    async def test_script_issues_bound_token(self, arch):
        username = f"build-node-{uuid.uuid4().hex[:8]}"
        own = node_name()
        token = await self.run_token_script("-u", username, "-n", own)
        assert "exp" not in self.token_claims(token)
        response = await self.ping_as(token, arch, own)
        assert response.status_code == 200, response.text
        response = await self.ping_as(token, arch, node_name())
        assert response.status_code == 403, response.text
        # One more token of the user keeps its binding
        again = await self.run_token_script("-u", username)
        response = await self.ping_as(again, arch, node_name())
        assert response.status_code == 403, response.text
        response = await self.ping_as(again, arch, own)
        assert response.status_code == 200, response.text
        with pytest.raises(SystemExit, match="is bound to"):
            await self.run_token_script("-u", username, "-n", node_name())

    async def test_script_token_with_lifetime(self, arch):
        token = await self.run_token_script(
            "-u", f"build-nodes-{uuid.uuid4().hex[:8]}",
            "--lifetime-days", "2",
        )
        expires_in = self.token_claims(token)["exp"] - time.time()
        assert 2 * 86400 - 60 < expires_in <= 2 * 86400
        response = await self.ping_as(token, arch, node_name())
        assert response.status_code == 200, response.text

    async def test_script_refuses_other_users(self):
        with pytest.raises(SystemExit, match="not a build node user"):
            await self.run_token_script("-u", "user1")

    async def test_deactivated_node_user_is_rejected(
        self,
        arch,
        session_factory,
        build_node_user,
    ):
        token, user_id = await build_node_user()
        name = node_name()
        response = await self.ping_as(token, arch, name)
        assert response.status_code == 200, response.text
        async with session_factory() as session:
            await session.execute(
                update(models.User)
                .where(models.User.id == user_id)
                .values(is_active=False, is_verified=False)
            )
            await session.commit()
        response = await self.ping_as(token, arch, name)
        assert response.status_code == 401, response.text


@pytest.mark.anyio
class TestQueuedAt:
    async def test_removed_dependency_requeues_task(
        self,
        seed_tasks,
        session_factory,
    ):
        """The wait of a task starts when its last dependency is gone."""
        old = datetime.datetime.utcnow() - datetime.timedelta(hours=1)
        first, second, third = await seed_tasks(3, queued_at=old)
        async with session_factory() as session:
            await session.execute(
                models.BuildTaskDependency.insert().values([
                    {"build_task_id": second, "build_task_dependency": first},
                    {"build_task_id": third, "build_task_dependency": second},
                ])
            )
            await session.commit()
        async with session_factory() as session:
            await build_node_crud.mark_dependent_tasks_queued(session, [first])
            await session.commit()
        async with session_factory() as session:
            tasks = {
                task.id: task
                for task in (
                    await session.execute(
                        select(models.BuildTask).where(
                            models.BuildTask.id.in_([first, second, third])
                        )
                    )
                ).scalars()
            }
        assert tasks[first].queued_at == old
        assert tasks[second].queued_at > old
        assert tasks[third].queued_at == old

import pytest

from alws.constants import BuildTaskStatus
from alws.crud.build import create_build
from alws.dramatiq.build import _start_build
from alws.dramatiq.products import (
    group_tasks_by_ref_id,
    get_packages_to_blacklist
)
from alws.models import (
    Build,
    BuildTask,
    BuildTaskArtifact
)
from alws.schemas.build_schema import BuildCreate

from sqlalchemy import insert, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from tests.constants import ADMIN_USER_ID
from tests.mock_classes import BaseAsyncTestCase

from typing import List, Tuple

from unittest.mock import Mock


def _create_build_task_mock(task: dict):
    return Mock(
        id=task["id"],
        ref_id=task["ref_id"],
        status=task["status"]
    )


group_tasks_by_ref_id_data_no_tasks = ([], {})

group_tasks_by_ref_id_data_all_success = (
    [
        _create_build_task_mock(
            {
                "id": 1,
                "ref_id": 1,
                "status": BuildTaskStatus.COMPLETED
            }
        ),
        _create_build_task_mock(
            {
                "id": 2,
                "ref_id": 1,
                "status": BuildTaskStatus.COMPLETED
            }
        ),
        _create_build_task_mock(
            {
                "id": 3,
                "ref_id": 2,
                "status": BuildTaskStatus.COMPLETED
            }
        ),
        _create_build_task_mock(
            {
                "id": 4,
                "ref_id": 2,
                "status": BuildTaskStatus.COMPLETED
            }
        ),
    ],
    {
        1: [
            (1, True),
            (2, True)
        ],
        2: [
            (3, True),
            (4, True)
        ]
    }
)

group_tasks_by_ref_id_data_refs_have_one_failed = (
    [
        _create_build_task_mock(
            {
                "id": 5,
                "ref_id": 3,
                "status": BuildTaskStatus.COMPLETED
            }
        ),
        _create_build_task_mock(
            {
                "id": 6,
                "ref_id": 3,
                "status": BuildTaskStatus.FAILED
            }
        ),
        _create_build_task_mock(
            {
                "id": 7,
                "ref_id": 4,
                "status": BuildTaskStatus.FAILED
            }
        ),
        _create_build_task_mock(
            {
                "id": 8,
                "ref_id": 4,
                "status": BuildTaskStatus.COMPLETED
            }
        ),
    ],
    {
        3: [
            (5, True),
            (6, False)
        ],
        4: [
            (7, False),
            (8, True)
        ]
    }
)

group_tasks_by_ref_id_data_refs_one_failed_all = (
    [
        _create_build_task_mock(
            {
                "id": 9,
                "ref_id": 5,
                "status": BuildTaskStatus.COMPLETED
            }
        ),
        _create_build_task_mock(
            {
                "id": 10,
                "ref_id": 5,
                "status": BuildTaskStatus.FAILED
            }
        ),
        _create_build_task_mock(
            {
                "id": 11,
                "ref_id": 6,
                "status": BuildTaskStatus.FAILED
            }
        ),
        _create_build_task_mock(
            {
                "id": 12,
                "ref_id": 6,
                "status": BuildTaskStatus.FAILED
            }
        ),
    ],
    {
        5: [
            (9, True),
            (10, False)
        ],
        6: [
            (11, False),
            (12, False)
        ]
    }
)

build_task_artifacts = [
    {
        "name": "package_1.src.rpm",
        "type": "rpm",
        "href": "/pulp/api/v3/content/rpm/packages/e735b845-d850-4a0a-8b5b-ae8b7e237275/",
    },
    {
        "name": "package_1.src.rpm",
        "type": "rpm",
        "href": "/pulp/api/v3/content/rpm/packages/e735b845-d850-4a0a-8b5b-ae8b7e237275/",
    },
    {
        "name": "package_2.src.rpm",
        "type": "rpm",
        "href": "/pulp/api/v3/content/rpm/packages/03d2eb4b-57b7-4ace-a5c4-4c193ab7f688/",
    },
    {
        "name": "package_2.src.rpm",
        "type": "rpm",
        "href": "/pulp/api/v3/content/rpm/packages/03d2eb4b-57b7-4ace-a5c4-4c193ab7f688/",
    },
    {
        "name": "package_3.src.rpm",
        "type": "rpm",
        "href": "/pulp/api/v3/content/rpm/packages/e0315db4-27c6-4f6b-b5b7-56fd5afecd72/",
    },
    {
        "name": "package_3.src.rpm",
        "type": "rpm",
        "href": "/pulp/api/v3/content/rpm/packages/e0315db4-27c6-4f6b-b5b7-56fd5afecd72/",
    },
    {
        "name": "package_4.src.rpm",
        "type": "rpm",
        "href": "/pulp/api/v3/content/rpm/packages/75432159-188f-46c3-8319-a5a480a0ded5/",
    },
    {
        "name": "package_4.src.rpm",
        "type": "rpm",
        "href": "/pulp/api/v3/content/rpm/packages/75432159-188f-46c3-8319-a5a480a0ded5/",
    },
    {
        "name": "package_5.src.rpm",
        "type": "rpm",
        "href": "/pulp/api/v3/content/rpm/packages/0eab3b59-7834-44d3-af19-37dbbda334c0/",
    },
    {
        "name": "package_5.src.rpm",
        "type": "rpm",
        "href": "/pulp/api/v3/content/rpm/packages/0eab3b59-7834-44d3-af19-37dbbda334c0/",
    },
    {
        "name": "package_6.src.rpm",
        "type": "rpm",
        "href": "/pulp/api/v3/content/rpm/packages/912b29e1-cd8a-4c51-b2e0-60a0e0657a1f/",
    },
    {
        "name": "package_6.src.rpm",
        "type": "rpm",
        "href": "/pulp/api/v3/content/rpm/packages/912b29e1-cd8a-4c51-b2e0-60a0e0657a1f/",
    },
]

build = {
        "platforms": [
            {
                "name": "AlmaLinux-8",
                "arch_list": ["x86_64", "i686"],
                "parallel_mode_enabled": False,
            }
        ],
        "tasks": [
            {
                "id": 1,
                "url": "https://build.task.ref#1"
            },
            {
                "id": 2,
                "url": "https://build.task.ref#2"
            },
            {
                "id": 3,
                "url": "https://build.task.ref#3"
            },
            {
                "id": 4,
                "url": "https://build.task.ref#4"
            },
            {
                "id": 5,
                "url": "https://build.task.ref#5"
            },
            {
                "id": 6,
                "url": "https://build.task.ref#6"
            }
        ],
        "linked_builds": [],
        "is_secure_boot": True,
        "mock_options": {},
        "platform_flavors": [],
        "product_id": 1,
    }


@pytest.mark.skip(
    reason="need to refactor due to build_task_dep unique constraint violation"
)
class TestProductsUnit(BaseAsyncTestCase):

    @pytest.mark.parametrize(
        "build_tasks, expected",
        [
            group_tasks_by_ref_id_data_no_tasks,
            group_tasks_by_ref_id_data_all_success,
            group_tasks_by_ref_id_data_refs_have_one_failed,
            group_tasks_by_ref_id_data_refs_one_failed_all
        ]
    )
    async def test_group_tasks_by_ref_id(self, build_tasks, expected):
        grouped_tasks = dict(group_tasks_by_ref_id(build_tasks))
    
        message = f"Expected {expected}, got {grouped_tasks}"
        assert grouped_tasks == expected, message
    

    @pytest.fixture()
    async def create_build_and_artifacts(
        self,
        session: AsyncSession,
        base_platform,
        base_product,
        create_build_rpm_repo,
        create_log_repo,
        modify_repository
    ) -> Build:
        created_build = await create_build(
            session,
            BuildCreate(**build),
            user_id=ADMIN_USER_ID
        )
        await _start_build(created_build.id, BuildCreate(**build))

        db_build = (await session.execute(
            select(Build).where(Build.id == created_build.id).options(
                selectinload(Build.tasks)
            )
        )).scalars().first()

        for task, artifact in zip(db_build.tasks, build_task_artifacts):
            artifact["build_task_id"] = task.id
            await session.execute(insert(BuildTaskArtifact).values(**artifact))
            await session.commit()

        return db_build


    @pytest.fixture
    async def tasks_and_expected_output(
        self,
        session: AsyncSession,
        create_build_and_artifacts,
        request
    ) -> Tuple[List[BuildTask], List[str]]:
        db_build = (await session.execute(
            select(Build).where(Build.id == create_build_and_artifacts.id).options(
                selectinload(Build.tasks)
            )
        )).scalars().first()
        if request.param == "all_completed":
            for task in db_build.tasks:
                task.status = BuildTaskStatus.COMPLETED
            expected_output = []
        elif request.param == "all_failed":
            for task in db_build.tasks:
                task.status = BuildTaskStatus.FAILED
            expected_output = set(
                [artifact["href"] for artifact in build_task_artifacts]
            )
        elif request.param == "first_ref_one_task_completed":
            db_build.tasks[0].status = BuildTaskStatus.COMPLETED
            expected_output = set(
                [
                    artifact["href"] for artifact
                    in build_task_artifacts
                    if not artifact["href"].endswith("ae8b7e237275/")
                ]
            )
        elif request.param == "first_and_second_refs_one_task_completed":
            db_build.tasks[0].status = BuildTaskStatus.COMPLETED
            db_build.tasks[2].status = BuildTaskStatus.COMPLETED
            expected_output = set(
                [
                    artifact["href"] for artifact
                    in build_task_artifacts
                    if not artifact["href"].endswith("ae8b7e237275/")
                    and not artifact["href"].endswith("4c193ab7f688/")
                ]
            )
        return db_build.tasks, expected_output


    @pytest.mark.parametrize(
        "tasks_and_expected_output",
        [
            "all_completed",
            "all_failed",
            "first_ref_one_task_completed",
            "first_and_second_refs_one_task_completed"
        ],
        indirect=True
    )
    async def test_get_packages_to_blacklist(self, tasks_and_expected_output, session):
        tasks, expected = tasks_and_expected_output
        pkgs_to_blacklist = await get_packages_to_blacklist(session, tasks)
        message = f"Expected {expected}, got {pkgs_to_blacklist}"
        assert sorted(pkgs_to_blacklist) == sorted(expected), message

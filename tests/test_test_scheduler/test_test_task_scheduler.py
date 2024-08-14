from typing import List, Optional
from unittest.mock import Mock

import pytest

from alws.crud.test import get_repos_for_test_task

# TODO: Move all this into a separate data file for unit tests
# when extending testing coverage for TestTaskScheduler
build_repos = [
    {
        "name": "build_repo_0",
        "type": "rpm",
        "arch": "x86_64",
        "url": "http://example.com/build_repo_0",
    },
    {
        "name": "build_repo_1",
        "type": "rpm",
        "arch": "noarch",
        "url": "http://example.com/build_repo_1",
    },
    {
        "name": "build_repo_2",
        "type": "rpm",
        "arch": "s390x",
        "url": "http://example.com/build_repo_2",
    },
    {
        "name": "build_repo_3",
        "type": "deb",
        "arch": "x86_64",
        "url": "http://example.com/build_repo_3",
    },
]

linked_builds = [
    {
        "repos": [
            {
                "name": "linked_build_repo_0",
                "type": "rpm",
                "arch": "x86_64",
                "url": "http://example.com/linked_build_repo_0",
            },
            {
                "name": "linked_build_repo_1",
                "type": "deb",
                "arch": "x86_64",
                "url": "http://example.com/linked_build_repo_1",
            },
        ]
    },
    {
        "repos": [
            {
                "name": "linked_build_repo_2",
                "type": "rpm",
                "arch": "x86_64",
                "url": "http://example.com/linked_build_repo_2",
            },
            {
                "name": "linked_build_repo_3",
                "type": "deb",
                "arch": "x86_64",
                "url": "http://example.com/linked_build_repo_3",
            },
        ]
    },
]

platform_flavors = [
    {
        "repos": [
            {
                "name": "platform_flavor_repo_0",
                "type": "rpm",
                "arch": "x86_64",
                "url": "http://example.com/$releasever/platform_flavor_repo_0",
            },
            {
                "name": "platform_flavor_repo_1",
                "type": "deb",
                "arch": "x86_64",
                "url": "http://example.com/$releasever/platform_flavor_repo_1",
            },
        ]
    },
    {
        "repos": [
            {
                "name": "platform_flavor_repo_2",
                "type": "rpm",
                "arch": "x86_64",
                "url": "http://example.com/$releasever/platform_flavor_repo_2",
            },
            {
                "name": "platform_flavor_repo_3",
                "type": "deb",
                "arch": "x86_64",
                "url": "http://example.com/$releasever/platform_flavor_repo_3",
            },
        ]
    },
]

platform_repos = [
    {
        "name": "platform_repo_0",
        "type": "rpm",
        "arch": "x86_64",
        "url": "http://example.com/platform_repo_0",
    },
    {
        "name": "platform_repo_1",
        "type": "rpm",
        "arch": "noarch",
        "url": "http://example.com/platform_repo_1",
    },
    {
        "name": "platform_repo_2",
        "type": "rpm",
        "arch": "s390x",
        "url": "http://example.com/platform_repo_2",
    },
    {
        "name": "platform_repo_3",
        "type": "deb",
        "arch": "x86_64",
        "url": "http://example.com/platform_repo_3",
    },
]

expected_build_repos = [{
    "name": "build_repo_0",
    "baseurl": "http://example.com/build_repo_0",
}]

expected_linked_builds_repos = [
    {
        "name": "linked_build_repo_0",
        "baseurl": "http://example.com/linked_build_repo_0",
    },
    {
        "name": "linked_build_repo_2",
        "baseurl": "http://example.com/linked_build_repo_2",
    },
]

expected_platform_flavors_repos = [
    {
        "name": "platform_flavor_repo_0",
        "baseurl": "http://example.com/8/platform_flavor_repo_0",
    },
    {
        "name": "platform_flavor_repo_2",
        "baseurl": "http://example.com/8/platform_flavor_repo_2",
    },
]


expected_platform_repos = [
    {
        "name": "platform_repo_0",
        "baseurl": "http://example.com/platform_repo_0",
    },
    {
        "name": "platform_repo_3",
        "baseurl": "http://example.com/platform_repo_3",
    },
]


def _create_mock_repo(repo):
    mock_repo = Mock(type=repo["type"], arch=repo["arch"], url=repo["url"])
    # We need to do this because "name" has a special meaning
    # for Mock objects
    mock_repo.name = repo["name"]
    return mock_repo


def create_test_task_with_repos_mock(
    build_repos: dict,
    linked_builds: Optional[List[dict]] = None,
    platform_flavors: Optional[List[dict]] = None,
) -> Mock:
    task = Mock()

    task.build_task.build.repos = []
    for repo in build_repos:
        mock_repo = _create_mock_repo(repo)
        task.build_task.build.repos.append(mock_repo)

    task.build_task.build.linked_builds = []
    if linked_builds:
        for idx, linked_build in enumerate(linked_builds):
            task.build_task.build.linked_builds.append(Mock(repos=[]))
            for repo in linked_build['repos']:
                mock_repo = _create_mock_repo(repo)
                task.build_task.build.linked_builds[idx].repos.append(mock_repo)

    task.build_task.build.platform_flavors = []
    if platform_flavors:
        for idx, platform_flavor in enumerate(platform_flavors):
            task.build_task.build.platform_flavors.append(Mock(repos=[]))
            for repo in platform_flavor['repos']:
                mock_repo = _create_mock_repo(repo)
                task.build_task.build.platform_flavors[idx].repos.append(
                    mock_repo
                )

    task.build_task.platform.repos = []
    for repo in platform_repos:
        mock_repo = _create_mock_repo(repo)
        task.build_task.platform.repos.append(mock_repo)

    return task


def create_test_task_with_build_repos():
    task = create_test_task_with_repos_mock(build_repos)
    task.env_arch = "x86_64"

    return (task, expected_build_repos)


def create_test_task_with_build_and_linked_repos():
    task = create_test_task_with_repos_mock(build_repos, linked_builds)
    task.env_arch = "x86_64"
    expected_repos = []
    for repos in (expected_build_repos, expected_linked_builds_repos):
        expected_repos.extend(repos)

    return (task, expected_repos)


def create_test_task_with_build_linked_and_flavor_repos():
    task = create_test_task_with_repos_mock(
        build_repos,
        linked_builds,
        platform_flavors,
    )
    task.env_arch = "x86_64"
    # We need to set distr_version because flavor repos might
    # include $releasever in the url
    task.build_task.platform.distr_version = "8"

    expected_repos = []
    for repos in (
        expected_build_repos,
        expected_linked_builds_repos,
        expected_platform_flavors_repos,
    ):
        expected_repos.extend(repos)

    return (task, expected_repos)


def create_test_task_with_build_and_flavor_repos():
    task = create_test_task_with_repos_mock(
        build_repos,
        None,
        platform_flavors,
    )
    task.env_arch = "x86_64"
    # We need to set distr_version because flavor repos might
    # include $releasever in the url
    task.build_task.platform.distr_version = "8"

    expected_repos = []
    for repos in (expected_build_repos, expected_platform_flavors_repos):
        expected_repos.extend(repos)

    return (task, expected_repos)


@pytest.mark.parametrize(
    "task, expected_repos",
    [
        create_test_task_with_build_repos(),
        create_test_task_with_build_and_linked_repos(),
        create_test_task_with_build_linked_and_flavor_repos(),
        create_test_task_with_build_and_flavor_repos(),
    ],
)
def test_get_repos_for_test_task(task, expected_repos):
    expected_repos.extend(expected_platform_repos)
    repos = get_repos_for_test_task(task)
    assert repos == expected_repos

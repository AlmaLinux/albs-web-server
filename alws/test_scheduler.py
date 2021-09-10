import asyncio
import logging
import random
import threading
import traceback

from sqlalchemy.future import select
from sqlalchemy.orm import selectinload

from alws import models
from alws.config import settings
from alws.constants import TestTaskStatus
from alws.database import SyncSession
from alws.utils.alts_client import AltsClient


class TestTaskScheduler(threading.Thread):
    def __init__(self, term_event: threading.Event,
                 graceful_event: threading.Event):
        super().__init__()
        self._term_event = term_event
        self._graceful_event = graceful_event
        self._loop = asyncio.new_event_loop()
        self._alts_client = AltsClient(settings.alts_host, settings.alts_token)

    def run_async_func(self, func, *args, **kwargs):
        return self._loop.run_until_complete(func(*args, **kwargs))

    async def _schedule_tasks_for_execution(self):
        session = SyncSession()
        tasks_query = session.execute(
            select(models.TestTask).where(
                models.TestTask.status == TestTaskStatus.CREATED).options(
                selectinload(models.TestTask.build_task).selectinload(
                    models.BuildTask.build).selectinload(
                    models.Build.repos),
                selectinload(models.TestTask.build_task).selectinload(
                    models.BuildTask.build).selectinload(
                    models.Build.linked_builds),
                selectinload(models.TestTask.build_task).selectinload(
                    models.BuildTask.platform)
            ).limit(10)
        )
        tasks = tasks_query.scalars()
        updated_tasks = []
        for task in tasks:
            task.status = TestTaskStatus.STARTED
            repositories = [{'name': item.name, 'baseurl': item.url}
                            for item in task.build_task.build.repos
                            if item.type == 'rpm']
            for build in task.build_task.build.linked_builds:
                rpm_repos = [{'name': item.name, 'baseurl': item.url}
                             for item in build.repo
                             if item.type == 'rpm']
                repositories.extend(rpm_repos)
            platform = task.build_task.platform
            try:
                logging.error(f'Scheduling testing for {task.package_name}-'
                              f'{task.package_version}-{task.package_release}')
                callback_href = f'/api/v1/tests/{task.id}/result/'
                response = await self._alts_client.schedule_task(
                    platform.test_dist_name, platform.distr_version,
                    task.env_arch, task.package_name, task.package_version,
                    callback_href, package_release=task.package_release,
                    repositories=repositories)
                updated_tasks.append(task)
                logging.error(f'Got response from ALTS: {response}')
            except Exception as e:
                logging.error(f'Cannot schedule test task: {e}')
                logging.error(f'Traceback info: {traceback.format_exc()}')
        if updated_tasks:
            session.add_all(updated_tasks)
            session.commit()
        session.close()

    def run(self) -> None:
        self._term_event.wait(10)
        while not self._term_event.is_set() and \
                not self._graceful_event.is_set():
            try:
                self.run_async_func(self._schedule_tasks_for_execution)
            except Exception as e:
                logging.error(f'Error during scheduler loop: {e}')
                logging.error(f'Traceback: {traceback.format_exc()}')
            finally:
                self._term_event.wait(random.randint(5, 10))
        self._loop.close()

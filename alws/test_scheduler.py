import datetime
import logging
import random
import threading
import asyncio

from fastapi_sqla import open_session
from sqlalchemy.future import select
from sqlalchemy.orm import selectinload

from alws import models
from alws.config import settings
from alws.constants import TestTaskStatus
from alws.utils.alts_client import AltsClient


class TestTaskScheduler(threading.Thread):
    def __init__(self, term_event: threading.Event,
                 graceful_event: threading.Event):
        super().__init__()
        self._term_event = term_event
        self._graceful_event = graceful_event
        self._alts_client = AltsClient(settings.alts_host, settings.alts_token)

    async def _schedule_tasks_for_execution(self):
        updated_tasks = []
        with open_session() as session, session.begin():
            try:
                tasks_query = session.execute(
                    select(models.TestTask).where(
                        models.TestTask.status == TestTaskStatus.CREATED,
                    ).options(
                        selectinload(models.TestTask.build_task).selectinload(
                            models.BuildTask.build).selectinload(
                            models.Build.repos),
                        selectinload(models.TestTask.build_task).selectinload(
                            models.BuildTask.build).selectinload(
                            models.Build.linked_builds),
                        selectinload(models.TestTask.build_task).selectinload(
                            models.BuildTask.platform),
                        selectinload(models.TestTask.build_task).selectinload(
                            models.BuildTask.rpm_module),
                    ).limit(10)
                )
                for task in tasks_query.scalars():
                    task.status = TestTaskStatus.STARTED
                    repositories = [{'name': item.name, 'baseurl': item.url}
                                    for item in task.build_task.build.repos
                                    if item.type == 'rpm'
                                    and item.arch == task.env_arch]
                    for build in task.build_task.build.linked_builds:
                        rpm_repos = [{'name': item.name, 'baseurl': item.url}
                                     for item in build.repos
                                     if item.type == 'rpm'
                                     and item.arch == task.env_arch]
                        repositories.extend(rpm_repos)
                    platform = task.build_task.platform
                    module_info = task.build_task.rpm_module
                    module_name = module_info.name if module_info else None
                    module_stream = module_info.stream if module_info else None
                    module_version = module_info.version if module_info else None
                    try:
                        logging.debug(
                            'Scheduling testing for %s-%s-%s',
                            task.package_name, task.package_version,
                            task.package_release
                        )
                        callback_href = f'/api/v1/tests/{task.id}/result/'
                        response = await self._alts_client.schedule_task(
                            platform.test_dist_name,
                            platform.distr_version,
                            task.env_arch,
                            task.package_name,
                            task.package_version,
                            callback_href,
                            package_release=task.package_release,
                            repositories=repositories,
                            module_name=module_name,
                            module_stream=module_stream,
                            module_version=module_version,
                        )
                        updated_tasks.append(task)
                        logging.debug('Got response from ALTS: %s', response)
                    except Exception as e:
                        logging.exception('Cannot schedule test task: %s',
                                          str(e))
                    else:
                        task.scheduled_at = datetime.datetime.utcnow()
            except Exception as e:
                logging.exception('Cannot run scheduling loop: %s', str(e))
            finally:
                if updated_tasks:
                    session.add_all(updated_tasks)
                    session.commit()

    async def run(self) -> None:
        self._term_event.wait(10)
        while not self._term_event.is_set() and \
                not self._graceful_event.is_set():
            try:
                await self._schedule_tasks_for_execution()
            except Exception as e:
                logging.exception('Error during scheduler loop: %s', str(e))
            finally:
                await asyncio.sleep(random.randint(5, 10))

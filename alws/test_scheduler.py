import datetime
import logging
import typing
import random
import threading
import asyncio

from sqlalchemy.future import select
from sqlalchemy.orm import selectinload

from alws import models
from alws.config import settings
from alws.constants import TestTaskStatus
from alws.database import SyncSession
from alws.utils.alts_client import AltsClient


class TestTaskScheduler(threading.Thread):
    # Filter this class out of pytest
    __test__ = False

    def __init__(self, term_event: threading.Event,
                 graceful_event: threading.Event):
        super().__init__()
        self._term_event = term_event
        self._graceful_event = graceful_event
        self._alts_client = AltsClient(settings.alts_host, settings.alts_token)


    @staticmethod
    def get_repos_for_test_task(task: models.TestTask) -> typing.List[dict]:
        repos = []
        # Build task repos
        build_repositories = [
            {'name': item.name, 'baseurl': item.url}
            for item in task.build_task.build.repos
            if item.type == 'rpm'
            and item.arch == task.env_arch
        ]

        # Linked build repos
        linked_build_repos = [
            {'name': item.name, 'baseurl': item.url}
            for build in task.build_task.build.linked_builds
            for item in build.repos
            if item.type == 'rpm'
            and item.arch == task.env_arch
        ]

        # Flavor repos
        platform = task.build_task.platform
        flavor_repos = [
            {
                'name': item.name,
                'baseurl': item.url.replace(
                    '$releasever',
                    platform.distr_version
                )
            }
            for flavor in task.build_task.build.platform_flavors
            for item in flavor.repos
            if item.type == 'rpm'
            and item.arch == task.env_arch
        ]

        for repo_arr in (
            build_repositories,
            linked_build_repos,
            flavor_repos
        ):
            repos.extend(repo_arr)

        return repos


    async def _schedule_tasks_for_execution(self):
        updated_tasks = []
        with SyncSession() as session:
            with session.begin():
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
                                models.BuildTask.build).selectinload(
                                models.Build.platform_flavors).selectinload(
                                    models.PlatformFlavour.repos
                                ),
                            selectinload(models.TestTask.build_task).selectinload(
                                models.BuildTask.platform),
                            selectinload(models.TestTask.build_task).selectinload(
                                models.BuildTask.rpm_module),
                        ).limit(10)
                    )
                    for task in tasks_query.scalars():
                        platform = task.build_task.platform
                        module_info = task.build_task.rpm_module
                        module_name = module_info.name if module_info else None
                        module_stream = module_info.stream if module_info else None
                        module_version = module_info.version if module_info else None
                        repositories = self.get_repos_for_test_task(task)
                        task.status = TestTaskStatus.STARTED

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
                                test_configuration=task.build_task.ref.test_configuration
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

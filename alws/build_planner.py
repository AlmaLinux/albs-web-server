import asyncio
import typing
import collections

from sqlalchemy.orm import Session
from sqlalchemy.future import select

from alws import models
from alws.errors import DataNotFoundError
from alws.config import settings
from alws.schemas import build_schema
from alws.constants import BuildTaskStatus
from alws.utils.pulp_client import PulpClient


__all__ = ['BuildPlanner']


class BuildPlanner:

    def __init__(
                self,
                db: Session,
                user_id: int,
                platforms: typing.List[build_schema.BuildCreatePlatforms]
            ):
        self._db = db
        self._build = models.Build(user_id=user_id)
        self._task_index = 0
        self._request_platforms = {
            platform.name: platform.arch_list for platform in platforms
        }
        self._platforms = []
        self._tasks_cache = collections.defaultdict(list)

    async def load_platforms(self):
        platform_names = list(self._request_platforms.keys())
        self._platforms = await self._db.execute(select(models.Platform).where(
            models.Platform.name.in_(platform_names)))
        self._platforms = self._platforms.scalars().all()
        if len(self._platforms) != len(platform_names):
            found_platforms = {platform.name for platform in self._platforms}
            missing_platforms = ', '.join(
                name for name in platform_names if name not in found_platforms
            )
            raise DataNotFoundError(
                f'platforms: {missing_platforms} cannot be found in database'
            )

    async def create_build_repo(
                self,
                pulp_client: PulpClient,
                platform: models.Platform,
                arch: str,
                build: models.Build,
                repo_type: str,
                is_debug: typing.Optional[bool] = False,
                task_id: typing.Optional[int] = None
            ) -> models.Repository:
        suffix = 'br' if repo_type != 'build_log' else f'artifacts-{task_id}'
        debug_suffix = 'debug-' if is_debug else ''
        repo_name = (
            f'{platform.name}-{arch}-{self._build.id}-{debug_suffix}{suffix}'
        )
        if repo_type == 'rpm':
            repo_url, pulp_href = await pulp_client.create_build_rpm_repo(
                repo_name)
        else:
            repo_url, pulp_href = await pulp_client.create_build_log_repo(
                repo_name)
        repo = models.Repository(
            name=repo_name,
            url=repo_url,
            arch=arch,
            pulp_href=pulp_href,
            type=repo_type,
            debug=is_debug
        )
        await self._db.run_sync(self.sync_append_build_repo, repo)

    def sync_append_build_repo(self, db: Session, repo: models.BuildRepo):
        self._build.repos.append(repo)

    def sync_get_build_tasks(self, db: Session):
        return self._build.tasks

    async def init_build_repos(self):
        pulp_client = PulpClient(
            settings.pulp_host,
            settings.pulp_user,
            settings.pulp_password
        )
        tasks = []
        for platform in self._platforms:
            for arch in ['src'] + self._request_platforms[platform.name]:
                tasks.append(self.create_build_repo(
                    pulp_client,
                    platform,
                    arch,
                    self._build,
                    'rpm'
                ))
                if arch == 'src':
                    continue
                tasks.append(self.create_build_repo(
                    pulp_client,
                    platform,
                    arch,
                    self._build,
                    'rpm',
                    True
                ))
        for task in await self._db.run_sync(self.sync_get_build_tasks):
            tasks.append(self.create_build_repo(
                pulp_client,
                task.platform,
                task.arch,
                self._build,
                'build_log',
                task_id=task.id
            ))
        await asyncio.gather(*tasks)

    async def add_linked_builds(self, linked_build):
        self._build.linked_builds.append(linked_build)

    async def add_task(self, task: build_schema.BuildTask):
        ref = models.BuildTaskRef(**task.dict())
        for platform in self._platforms:
            arch_tasks = []
            for arch in self._request_platforms[platform.name]:
                build_task = models.BuildTask(
                    arch=arch,
                    platform_id=platform.id,
                    status=BuildTaskStatus.IDLE,
                    index=self._task_index,
                    ref=ref
                )
                task_key = (platform.name, arch)
                self._tasks_cache[task_key].append(build_task)
                if self._task_index > 0:
                    dep = self._tasks_cache[task_key][self._task_index - 1]
                    build_task.dependencies.append(dep)
                for dep in arch_tasks:
                    build_task.dependencies.append(dep)
                arch_tasks.append(build_task)
                self._build.tasks.append(build_task)
        self._task_index += 1

    def add_mock_options(self, mock_options: dict):
        self._build.mock_options = mock_options

    def create_build(self):
        return self._build

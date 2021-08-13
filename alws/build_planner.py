import os
import boto3
import asyncio
import typing
import itertools
import collections

from sqlalchemy.orm import Session
from sqlalchemy.future import select

from alws import models
from alws.config import settings
from alws.schemas import build_schema
from alws.constants import BuildTaskStatus
from alws.utils.pulp_client import PulpClient


__all__ = ['BuildPlanner']


def get_s3_build_directory(build_id: int, task_id: int) -> str:
    return os.path.join(
        settings.s3_artifacts_dir,
        str(build_id),
        str(task_id)
    ) + '/'


class BuildPlanner:

    def __init__(self, db: Session, user_id: int, platforms: typing.List[str]):
        self._db = db
        self._s3_client = boto3.client(
            's3',
            region_name=settings.s3_region,
            aws_access_key_id=settings.s3_access_key_id,
            aws_secret_access_key=settings.s3_secret_access_key
        )
        self._build = models.Build(user_id=user_id)
        self._task_index = 0
        self._platform_names = platforms
        self._platforms = []
        self._tasks_cache = collections.defaultdict(list)

    async def load_platforms(self):
        self._platforms = await self._db.execute(select(models.Platform).where(
            models.Platform.name.in_(self._platform_names)))
        self._platforms = self._platforms.scalars().all()
        if len(self._platforms) != len(self._platform_names):
            # TODO: raise error
            pass

    async def create_build_repo(
                self,
                pulp_client: PulpClient,
                platform: models.Platform,
                arch: str,
                build: models.Build
            ) -> models.Repository:
        repo_name = f'{platform.name}-{arch}-{self._build.id}-br'
        repo_url, pulp_href = await pulp_client.create_build_rpm_repo(
            repo_name)
        repo = models.Repository(
            name=repo_name,
            url=repo_url,
            arch=arch,
            pulp_href=pulp_href,
            type='rpm'
        )
        await self._db.run_sync(self.sync_append_build_repo, repo)

    def init_s3_build_directory(self, db: Session):
        for task in self._build.tasks:
            self._s3_client.put_object(
                Bucket=settings.s3_bucket,
                Key=get_s3_build_directory(self._build.id, task.id)
            )

    def sync_append_build_repo(self, db: Session, repo: models.BuildRepo):
        self._build.repos.append(repo)

    async def init_build_repos(self):
        pulp_client = PulpClient(
            settings.pulp_host,
            settings.pulp_user,
            settings.pulp_password
        )
        repos = []
        for platform in self._platforms:
            for arch in itertools.chain(('src', ), platform.arch_list):
                repos.append(self.create_build_repo(
                    pulp_client,
                    platform,
                    arch,
                    self._build
                ))
        await asyncio.gather(
            *repos,
            self._db.run_sync(self.init_s3_build_directory)
        )

    async def add_task(self, task: build_schema.BuildTask):
        ref = models.BuildTaskRef(**task.dict())
        for platform in self._platforms:
            arch_tasks = []
            for arch in platform.arch_list:
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

    def create_build(self):
        return self._build

import datetime
import typing

from pydantic import BaseModel, Field

from alws.utils.debuginfo import is_debuginfo_rpm

__all__ = ['Task']


class TaskRepo(BaseModel):
    name: str
    url: str
    priority: int
    mock_enabled: bool = True

    class Config:
        from_attributes = True


class TaskRef(BaseModel):
    url: str
    git_ref: typing.Optional[str] = None
    ref_type: int
    git_commit_hash: typing.Optional[str] = None

    class Config:
        from_attributes = True


class TaskCreatedBy(BaseModel):
    name: str
    email: str


class TaskPlatform(BaseModel):
    name: str
    type: typing.Literal['rpm', 'deb']
    data: typing.Dict[str, typing.Any]

    def add_mock_options(self, options):
        for k, v in options.items():
            if k == 'target_arch':
                self.data['mock'][k] = v
            elif k == 'module_enable':
                if not self.data['mock'].get(k):
                    self.data['mock'][k] = []
                if isinstance(v, list):
                    self.data['mock'][k].extend(v)
                else:
                    self.data['mock'][k].append(v)
                self.data['mock'][k] = list(set(self.data['mock'][k]))
            elif k == 'yum_exclude':
                old_exclude = self.data['yum'].get('exclude', '')
                full_exclude = f'{old_exclude} {" ".join(v)}'.strip()
                self.data['yum']['exclude'] = (
                    full_exclude if full_exclude else None
                )
            elif k in ('with', 'without'):
                for i in v:
                    self.data['definitions'][f'_{k}_{i}'] = f'--{k}-{i}'
            elif isinstance(v, dict):
                for v_k, v_v in v.items():
                    self.data['definitions'][v_k] = v_v

    class Config:
        from_attributes = True


class Task(BaseModel):
    id: int
    arch: str
    ref: TaskRef
    build_id: int
    platform: TaskPlatform
    created_by: TaskCreatedBy
    alma_commit_cas_hash: typing.Optional[str] = None
    srpm_hash: typing.Optional[str] = None
    is_cas_authenticated: bool = False
    is_secure_boot: typing.Optional[bool] = False
    repositories: typing.List[TaskRepo]
    linked_builds: typing.Optional[typing.List[int]] = []
    built_srpm_url: typing.Optional[str] = None

    class Config:
        from_attributes = True


class NodeInfo(BaseModel):
    version: typing.Optional[str] = None
    supported_arches: typing.List[str] = []
    # threads_count of the node
    capacity: int = 0
    node_type: typing.Optional[str] = None
    pesign_support: bool = False
    # /tmp/graceful_stop is present on the node
    maintenance: bool = False
    # hostname.pid of the node process
    instance_id: typing.Optional[str] = None
    # instance_id of the previous process of the node on the same host,
    # it tells a restart from another process with the same name
    previous_instance_id: typing.Optional[str] = None


class NodeResources(BaseModel):
    cpu_count: int
    # 1, 5 and 15 minutes
    load_avg: typing.List[float]
    mem_total_bytes: int
    mem_available_bytes: int
    # Working directory of the builds
    disk_path: str
    disk_total_bytes: int
    disk_free_bytes: int


class Ping(BaseModel):
    # Includes tasks waiting in the local queue of the node
    active_tasks: typing.List[int]
    node_name: typing.Optional[str] = None
    node_info: typing.Optional[NodeInfo] = None
    resources: typing.Optional[NodeResources] = None


class BuildDoneArtifact(BaseModel):
    name: str
    type: typing.Literal['rpm', 'build_log']
    href: str
    sha256: str
    cas_hash: typing.Optional[str] = None

    class Config:
        from_attributes = True

    @property
    def arch(self):
        # TODO: this is awful way to check pkg arch
        return self.name.split('.')[-2]

    @property
    def is_debuginfo(self):
        return is_debuginfo_rpm(self.name)


class BuildDone(BaseModel):
    task_id: int
    status: typing.Literal['done', 'failed', 'excluded']
    artifacts: typing.List[BuildDoneArtifact]
    stats: typing.Dict[str, typing.Dict[str, str]]
    is_cas_authenticated: bool = False
    alma_commit_cas_hash: typing.Optional[str] = None
    git_commit_hash: typing.Optional[str] = None
    node_name: typing.Optional[str] = None


class RequestTask(BaseModel):
    supported_arches: typing.List[str]
    excluded_packages: typing.Optional[typing.List[str]] = []
    node_name: typing.Optional[str] = None
    node_info: typing.Optional[NodeInfo] = None


class BuildNodeTask(BaseModel):
    id: int
    build_id: int
    arch: str
    ref_url: typing.Optional[str] = None
    claimed_at: typing.Optional[datetime.datetime] = None
    # Times the task was handed out to the nodes and the names of the
    # last ones (None for a node without node_name), see dispatch_count
    # and dispatch_nodes of the build task
    dispatch_count: int = 0
    dispatch_nodes: typing.List[typing.Optional[str]] = []


class BuildNodeRecentTask(BuildNodeTask):
    status: int
    finished_at: typing.Optional[datetime.datetime] = None


class BuildNodeStats(BaseModel):
    done: int = 0
    failed: int = 0
    excluded: int = 0


class BuildNode(BaseModel):
    id: int
    name: str
    enabled: bool
    drain: bool
    maintenance: bool
    online: bool
    last_seen: typing.Optional[datetime.datetime] = None
    version: typing.Optional[str] = None
    instance_id: typing.Optional[str] = None
    supported_arches: typing.List[str] = []
    node_type: typing.Optional[str] = None
    pesign_support: bool
    capacity: int
    capacity_override: typing.Optional[int] = None
    effective_capacity: int
    active_tasks_count: int
    resources: typing.Optional[NodeResources] = None
    resources_updated_at: typing.Optional[datetime.datetime] = None
    active_tasks: typing.List[BuildNodeTask] = []
    stats_24h: BuildNodeStats


class BuildNodeDetails(BuildNode):
    recent_tasks: typing.List[BuildNodeRecentTask] = []


class BuildNodeUpdate(BaseModel):
    enabled: typing.Optional[bool] = None
    drain: typing.Optional[bool] = None
    # null resets the limit, so it's applied only when it was sent
    capacity_override: typing.Optional[int] = Field(default=None, ge=0)


class BuildNodesQueue(BaseModel):
    arch: str
    queued_tasks: int
    online_nodes: int
    total_capacity: int
    # Every STARTED task that is being built somewhere
    active_tasks: int
    # Held by the nodes counted in online_nodes, comparable with
    # total_capacity
    accepting_active_tasks: int
    # Claimed by the nodes without node_name
    unregistered_active_tasks: int

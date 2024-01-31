# -*- mode:python; coding:utf-8; -*-
# author: Mariia Boldyreva <mboldyreva@cloudlinux.com>
# created: 2021-09-03

"""
AlmaLinux Build System Gitea queue validation models.
"""

import typing
from datetime import datetime

from pydantic import BaseModel

__all__ = [
    'GiteaListenerConfig',
    'ShortUser',
    'User',
    'PushedEvent',
    'Repository',
    'Commit',
]


class GiteaListenerConfig(BaseModel):
    """Gitea queue listener configuration validation."""

    mqtt_queue_host: str
    mqtt_queue_port: int
    mqtt_queue_topic_unmodified: str
    mqtt_queue_topic_modified: str
    mqtt_queue_qos: int
    mqtt_client_id: str
    mqtt_queue_username: typing.Optional[str] = None
    mqtt_queue_password: typing.Optional[str] = None
    mqtt_queue_clean_session: bool
    albs_jwt_token: typing.Optional[str] = None
    albs_address: str
    redis_host: str = 'redis://redis:6379'
    redis_cache_key: str = 'gitea_cache'


class ShortUser(BaseModel):
    """Shorted Gitea user validation."""

    name: str
    email: str
    username: str


class User(BaseModel):
    """Gitea user validation."""

    id: int
    login: str
    full_name: str
    email: str
    avatar_url: str
    username: str


class Repository(BaseModel):
    """Gitea repository validation."""

    id: int
    owner: User
    name: str
    full_name: str
    description: typing.Optional[str]
    private: bool
    fork: bool
    html_url: str
    ssh_url: str
    clone_url: str
    website: typing.Optional[str]
    stars_count: int
    forks_count: int
    watchers_count: int
    open_issues_count: int
    default_branch: str
    created_at: datetime
    updated_at: datetime


class Commit(BaseModel):
    """Gitea commit validation."""

    id: str
    message: str
    url: str
    author: ShortUser
    committer: ShortUser
    timestamp: datetime


class PushedEvent(BaseModel):
    """Received MQTT event validation."""

    secret: typing.Optional[str]
    ref: str = ''
    before: str = ''
    after: str = ''
    compare_url: str = ''
    commits: typing.List[Commit]
    repository: Repository
    pusher: User
    sender: User

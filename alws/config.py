import typing
import urllib.parse

from pydantic import BaseSettings


class Settings(BaseSettings):

    pulp_host: str = 'http://pulp'
    pulp_user: str = 'admin'
    pulp_password: str = 'admin'
    pulp_export_path: str = '/srv/exports'
    pulp_database_url: str = 'postgresql+psycopg2://postgres:password@pulp/pulp'

    alts_host: str = 'http://alts-scheduler:8000'
    alts_token: str
    gitea_host: str = 'https://git.almalinux.org/api/v1/'

    test_task_scheduler_enabled: bool = False

    package_beholder_enabled: bool = True
    beholder_host: typing.Optional[str] = 'http://beholder-web:5000'
    beholder_token: typing.Optional[str]

    redis_url: str = 'redis://redis:6379'

    database_url: str = 'postgresql+asyncpg://postgres:password@db/almalinux-bs'
    test_database_url: str = 'postgresql+asyncpg://postgres:password@db/test-almalinux-bs'
    sync_database_url: str = 'postgresql+psycopg2://postgres:password@db/almalinux-bs'

    github_client: str
    github_client_secret: str

    jwt_secret: str
    jwt_algorithm: str = 'HS256'

    cas_api_key: typing.Optional[str]
    cas_signer_id: typing.Optional[str]

    rabbitmq_default_user: str = 'test-system'
    rabbitmq_default_pass: str = 'test-system'
    rabbitmq_default_host: str = 'rabbitmq'
    rabbitmq_default_vhost: str = 'test_system'

    sign_server_url: typing.Optional[str] = 'http://web_server:8000/api/v1/'
    sign_server_token: typing.Optional[str]
    sign_file_token: typing.Optional[str]

    documentation_path: str = 'alws/documentation/'

    logging_level: typing.Optional[str] = 'INFO'

    frontend_baseurl: str = 'http://localhost:8080'
    github_callback_endpoint: str = 'api/v1/auth/github/callback'

    sentry_environment: str = 'dev'
    sentry_dsn: typing.Optional[str]
    sentry_traces_sample_rate: float = 0.2

    @property
    def codenotary_enabled(self) -> bool:
        return bool(self.cas_api_key) and bool(self.cas_signer_id)

    @property
    def github_callback_url(self) -> str:
        return urllib.parse.urljoin(
            settings.frontend_baseurl, settings.github_callback_endpoint)


settings = Settings()

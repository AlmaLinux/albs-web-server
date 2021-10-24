import typing

from pydantic import BaseSettings


class Settings(BaseSettings):

    pulp_host: str = 'http://pulp'
    pulp_user: str = 'admin'
    pulp_password: str = 'admin'
    alts_host: str = 'http://alts-scheduler:8000'
    alts_token: str

    redis_url: str = 'redis://redis:6379'

    beholder_host: str
    beholder_token: typing.Optional[str]

    database_url: str = 'postgresql+asyncpg://postgres:password@db/almalinux-bs'
    sync_database_url: str = 'postgresql+psycopg2://postgres:password@db/almalinux-bs'

    github_client: str
    github_client_secret: str

    jwt_secret: str
    jwt_algorithm: str = 'HS256'


settings = Settings()

from pydantic import BaseSettings


class Settings(BaseSettings):

    pulp_host: str = 'http://pulp'
    pulp_user: str = 'admin'
    pulp_password: str = 'admin'
    alts_host: str
    alts_token: str

    redis_url: str = 'redis://redis:6379'

    database_url: str = 'postgresql+asyncpg://postgres:password@db/almalinux-bs'
    sync_database_url: str = 'postgresql+psycopg2://postgres:password@db/almalinux-bs'

    github_client: str
    github_client_secret: str

    jwt_secret: str
    jwt_algorithm: str = 'HS256'


settings = Settings()

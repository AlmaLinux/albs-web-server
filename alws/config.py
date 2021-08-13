from pydantic import BaseSettings


class Settings(BaseSettings):

    pulp_host: str = 'http://pulp'
    pulp_user: str = 'admin'
    pulp_password: str = 'admin'

    database_url: str = 'postgresql+asyncpg://postgres:password@db/almalinux-bs'

    github_client: str
    github_client_secret: str

    jwt_secret: str
    jwt_algorithm: str = 'HS256'

    s3_region: str
    s3_bucket: str
    s3_artifacts_dir: str
    s3_access_key_id: str
    s3_secret_access_key: str


settings = Settings()

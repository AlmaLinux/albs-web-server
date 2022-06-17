from pydantic import BaseSettings


class Config(BaseSettings):
    cache_interval: int = 10  # Minutes
    albs_jwt_token: str = ""
    albs_api_url: str = "http://web_server:8000/api/v1/"
    base_security_api_url: str = (
        "https://access.redhat.com/hydra/rest/securitydata/"
    )


config = Config()

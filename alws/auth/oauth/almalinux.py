from httpx_oauth.clients.openid import OpenID

__all__ = [
    'get_almalinux_oauth_client'
]

SCOPES = [
    'openid',
    'profile',
]

CONFIG_URL = 'https://id.almalinux.org/realms/master/.well-known/openid-configuration'

def get_almalinux_oauth_client(client_id: str, client_secret: str):
    return OpenID(
        client_id, client_secret,
        CONFIG_URL,
        base_scopes=SCOPES,
    )

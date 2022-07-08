from typing import (
    Any,
    Dict,
    List,
    Optional,
    cast
)

from httpx_oauth.clients.github import GitHubOAuth2, BASE_SCOPES
from httpx_oauth.oauth2 import GetAccessTokenError, OAuth2Token


__all__ = [
    'get_github_oauth_client'
]


SCOPES = [
    'read:user',
    'user:email',
    'read:org'
]


class ALBSGithubClient(GitHubOAuth2):
    def __init__(self, client_id: str, client_secret: str,
                 scopes: Optional[List[str]] = BASE_SCOPES,
                 name: str = 'github'):
        super().__init__(client_id, client_secret, scopes=scopes, name=name)
    
    async def get_access_token(
        self, code: str, redirect_uri: str, code_verifier: str = None
    ):
        async with self.get_httpx_client() as client:
            data = {
                'grant_type': 'authorization_code',
                'code': code,
                'client_id': self.client_id,
                'client_secret': self.client_secret,
            }
            if redirect_uri:
                data['redirect_uri'] = redirect_uri
            if code_verifier:
                data['code_verifier'] = code_verifier

            response = await client.post(
                self.access_token_endpoint,
                data=data,
                headers=self.request_headers,
            )

            data = cast(Dict[str, Any], response.json())

            if response.status_code == 400:
                raise GetAccessTokenError(data)

            return OAuth2Token(data)


def get_github_oauth_client(client_id: str, client_secret: str):
    return ALBSGithubClient(client_id, client_secret, scopes=SCOPES)

from httpx_oauth.clients.github import GitHubOAuth2


__all__ = [
    'get_github_oauth_client'
]


SCOPES = [
    'user:email',
    'read:org'
]


def get_github_oauth_client(client_id: str, client_secret: str):
    return GitHubOAuth2(client_id, client_secret, scopes=SCOPES)

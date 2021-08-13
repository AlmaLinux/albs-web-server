import aiohttp


async def get_user_github_token(
            code: str,
            client_id: str,
            client_secret: str
        ) -> str:
    client_secrets_endpoint = 'https://github.com/login/oauth/access_token'
    payload = {
        'code': code,
        'client_id': client_id,
        'client_secret': client_secret
    }
    headers = {'accept': 'application/json'}
    async with aiohttp.ClientSession() as session:
        async with session.post(
                client_secrets_endpoint,
                json=payload,
                headers=headers) as response:
            response.raise_for_status()
            return (await response.json())['access_token']


async def get_github_user_info(token: str):
    user_endpoint = 'https://api.github.com/user'
    headers = {'authorization': f'token {token}'}
    async with aiohttp.ClientSession() as session:
        async with session.get(user_endpoint, headers=headers) as response:
            response.raise_for_status()
            response = await response.json()
    response['email'] = (await get_github_user_emails(token))[0]['email']
    response['organizations'] = await get_github_user_organizations(
        response['organizations_url'])
    return response


async def get_github_user_emails(token: str):
    user_endpoint = 'https://api.github.com/user/emails'
    headers = {'authorization': f'token {token}'}
    async with aiohttp.ClientSession() as session:
        async with session.get(user_endpoint, headers=headers) as response:
            response.raise_for_status()
            return await response.json()


async def get_github_user_organizations(url: str):
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as response:
            response.raise_for_status()
            return await response.json()

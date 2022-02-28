import os
import json
import urllib.parse
import aiohttp

from lxml import etree
from syncer import sync

from alws import database
from alws.config import settings
from alws.routers.sign_key import get_sign_keys


HEADERS = {'Authorization': f'Bearer {settings.sign_server_token}'}


async def sign_repomd_xml(data):
    endpoint = 'sign-tasks/sync_sign_task/'
    url = urllib.parse.urljoin(settings.sign_server_url, endpoint)
    async with aiohttp.ClientSession(headers=HEADERS,
                                     raise_for_status=True) as session:
        async with session.post(url, json=data) as response:
            json_data = await response.read()
            json_data = json.loads(json_data)
            return json_data


async def get_sign_keys_from_db():
    async with database.Session() as session:
        return await get_sign_keys(session)


def repomd_signer(export_path, key_id):
    xml = etree.parse(os.path.join(export_path, 'repomd.xml'))
    xml_string = str(etree.tostring(xml.getroot()))
    sign_data = {
        "content": xml_string,
        "pgp_keyid": key_id,
    }
    result = sync(sign_repomd_xml(sign_data))
    print(result)
    result_data = result.get('asc_content')
    repodata_path = os.path.join(export_path, 'repomd.xml.asc')
    if result_data is not None:
        with open(repodata_path, 'w') as file:
            file.writelines(result_data)

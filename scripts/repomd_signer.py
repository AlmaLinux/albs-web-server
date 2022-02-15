import os
import aioredis

from lxml import etree
from syncer import sync

from alws import database
from alws.config import settings
from alws.schemas import sign_schema
from alws.routers.sign_task import create_small_sign_task
from alws.routers.sign_key import get_sign_keys


async def sign_repomd_xml(data):
    client = aioredis.from_url(settings.redis_url)
    return await create_small_sign_task(
        sign_schema.SyncSignTaskRequest(**data), client)


async def get_sign_keys_from_db():
    async with database.Session() as session:
        return await get_sign_keys(session)


def repomd_signer(export_path):
    xml = etree.parse(os.path.join(export_path, 'repomd.xml'))
    xml_string = str(etree.tostring(xml.getroot()))
    # for production we need fetch sign_key by platform_id
    sign_key = sync(get_sign_keys_from_db())[0]
    sign_data = {
        "content": xml_string,
        "pgp_keyid": sign_key.keyid,
    }
    result = sync(sign_repomd_xml(sign_data))
    print(result)
    result_data = result.get('asc_content')
    config_path = os.path.join(export_path, 'repomd.xml.asc')
    if result_data is not None:
        with open(config_path, 'w') as file:
            file.writelines(result_data)

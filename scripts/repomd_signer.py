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


def repomd_signer(export_path, platforms_dict):
    xml = etree.parse(os.path.join(export_path, 'repomd.xml'))
    xml_string = str(etree.tostring(xml.getroot()))
    sign_keys = sync(get_sign_keys_from_db())
    key_id = None
    # TODO: need to refactor this
    if 'almalinux-8' in str(export_path):
        platform_id = platforms_dict.get('AlmaLinux-8', 0)
        key_id = next((
            sign_key.keyid for sign_key in sign_keys
            if sign_key.platform_id == platform_id
        ), None)
    elif 'almalinux-9' in str(export_path):
        platform_id = platforms_dict.get('AlmaLinux-9', 0)
        key_id = next((
            sign_key.keyid for sign_key in sign_keys
            if sign_key.platform_id == platform_id
        ), None)
    if key_id is None:
        raise Exception
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

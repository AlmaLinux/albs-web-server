import aiohttp
import hashlib

from typing import BinaryIO


async def download_log(url: str) -> bytes:
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as response:
            content = await response.read()
            response.raise_for_status()
            return content


async def download_file(url: str, dest: BinaryIO):
    """
    Download file by url and write it to destination

    Parameters
    ----------
    url : str
        Url of file to download
    dest: BinaryIO
        Destination to write file

    Returns
    -------

    """
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as response:
            content = await response.content.read()
            dest.write(content)


def hash_content(content):
    hasher = hashlib.new('sha256')
    if isinstance(content, bytes):
        hasher.update(content)
    else:
        hasher.update(content.encode())
    return hasher.hexdigest()

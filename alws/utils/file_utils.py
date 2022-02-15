import aiohttp

from typing import BinaryIO


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

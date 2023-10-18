import typing

import pytest
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from alws.crud.sign_key import create_sign_key
from alws.models import Platform, SignKey
from alws.schemas.sign_schema import SignKeyCreate


BASIC_SIGN_KEY_PAYLOAD = {
    "name": "Test key",
    "description": "Test sign key",
    "keyid": "1234567890ABCDEF",
    "fingerprint": "1234567890ABCDEF1234567890ABCDEF12345678",
    "public_url": "no_url",
}


async def __create_sign_key(session: AsyncSession, payload: dict) -> SignKey:
    await create_sign_key(session, SignKeyCreate(**payload))
    sign_key = (await session.execute(select(SignKey).where(
        SignKey.keyid == payload['keyid']))).scalars().first()
    return sign_key


@pytest.mark.anyio
@pytest.fixture
async def sign_key(
    session: AsyncSession,
) -> typing.AsyncIterable[SignKey]:
    sign_key = await __create_sign_key(session, BASIC_SIGN_KEY_PAYLOAD)
    yield sign_key
    await session.execute(delete(SignKey))
    await session.commit()


@pytest.mark.anyio
@pytest.fixture
async def sign_key_with_platform(
    session: AsyncSession,
    base_platform: Platform,
) -> typing.AsyncIterable[SignKey]:
    payload = BASIC_SIGN_KEY_PAYLOAD.copy()
    payload['platform_id'] = str(base_platform.id)
    sign_key = await __create_sign_key(session, payload)
    yield sign_key

import typing

import pytest
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from alws.crud.sign_key import create_sign_key
from alws.models import SignKey
from alws.schemas.sign_schema import SignKeyCreate


@pytest.fixture
def basic_sign_key_payload() -> dict:
    return {
        "name": "Test key",
        "description": "Test sign key",
        "keyid": "1234567890ABCDEF",
        "fingerprint": "1234567890ABCDEF1234567890ABCDEF12345678",
        "public_url": "no_url",
    }


async def __create_sign_key(session: AsyncSession, payload: dict) -> SignKey:
    await create_sign_key(session, SignKeyCreate(**payload))
    sign_key_cursor = await session.execute(
        select(SignKey).where(SignKey.keyid == payload['keyid'])
    )
    sign_key = sign_key_cursor.scalars().first()
    return sign_key


@pytest.mark.anyio
@pytest.fixture
async def sign_key(
    session: AsyncSession,
    basic_sign_key_payload,
) -> typing.AsyncIterable[SignKey]:
    sign_key = await __create_sign_key(session, basic_sign_key_payload)
    yield sign_key
    await session.execute(delete(SignKey))
    await session.commit()

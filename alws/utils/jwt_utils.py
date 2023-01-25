import time
import typing

import jwt


def generate_JWT_token(
    user_id: str,
    jwt_secret: str,
    jwt_algorithm: str,
) -> str:
    payload = {
        # TODO: this is wrong
        "sub": user_id,
        "exp": time.time() + 60000,
        "aud": ["fastapi-users:auth"],
    }
    return jwt.encode(payload, jwt_secret, algorithm=jwt_algorithm)


def decode_JWT_token(
    token: str,
    jwt_secret: str,
    jwt_algorithm: str,
) -> typing.Optional[dict]:
    decoded_token = jwt.decode(token, jwt_secret, algorithms=[jwt_algorithm])
    # TODO: this is wrong
    if decoded_token["exp"] <= time.time():
        return
    return decoded_token

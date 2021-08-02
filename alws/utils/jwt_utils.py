import time

import jwt


def generate_JWT_token(
            identity: dict,
            jwt_secret: str,
            jwt_algorithm: str,
        ) -> str:
    payload = {
        # TODO: this is wrong
        'expires': time.time() + 60000,
        'identity': identity
    }
    return jwt.encode(payload, jwt_secret, algorithm=jwt_algorithm)


def decode_JWT_token(
            token: str,
            jwt_secret: str,
            jwt_algorithm: str
        ) -> dict:
    decoded_token = jwt.decode(token, jwt_secret, algorithms=[jwt_algorithm])
    # TODO: this is wrong
    if decoded_token['expires'] <= time.time():
        return
    return decoded_token

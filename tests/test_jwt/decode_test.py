import unittest
from jwt.exceptions import InvalidSignatureError

from alws.utils import jwt_utils


class TestJWTToken(unittest.TestCase):

    def test_decode_JWT_token(self):
        initial_JWT_token = jwt_utils.generate_JWT_token(
            {'user_id': 1}, 'sector', 'HS256')
        decoded_JWT_token = jwt_utils.decode_JWT_token(
            initial_JWT_token, 'sector', 'HS256')
        identity = {'user_id': 1}
        message = "JWT token wasn't decoded correctly with correct secret"
        self.assertEqual(decoded_JWT_token['identity'], identity, message)

    def test_fail_decode_JWT_token(self):
        initial_JWT_token = jwt_utils.generate_JWT_token(
            {'user_id': 1}, 'sector', 'HS256')
        with self.assertRaises(InvalidSignatureError):
            jwt_utils.decode_JWT_token(
                initial_JWT_token, 'SECTOR', 'HS256')

import os
import tempfile

from alws.models import SignKey
from scripts.packages_exporter import Exporter
from tests.mock_classes import BaseAsyncTestCase

IN_GITHUB_ACTIONS = os.getenv("GITHUB_ACTIONS") is not None


class TestPackagesExporter(BaseAsyncTestCase):
    async def test_repomd_signer(self, sign_key: SignKey):
        exporter = Exporter(
            pulp_client=None, repodata_cache_dir='~/.cache/pulp_exporter'
        )
        key_id = sign_key.keyid
        token = await exporter.get_sign_server_token()
        with tempfile.NamedTemporaryFile() as fp:
            fp.write(b'Hello world!')
            res = await exporter.sign_repomd_xml(fp.name, key_id, token)
            assert res['error'] is None
